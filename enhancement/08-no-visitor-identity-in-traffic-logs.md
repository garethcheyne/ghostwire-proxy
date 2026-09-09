# 08 — `TrafficLog.auth_user` is never written, so there is no visitor identity

**Severity:** Medium
**Status:** **Partial** (2026-09-09) — authenticated hosts done; public-host opt-in still open. See [README](README.md#partial).
**Answers:** "is there a way to track a unique user, not just the IP address?"

## TL;DR

`TrafficLog` has an `auth_user` column and the API returns it. Nothing ever
populates it, so every row is NULL and there is no way to attribute traffic to a
person rather than an address.

The identity already exists and is thrown away. The auth wall issues a signed
session cookie (`gw_auth_session`) backed by an `auth_wall_sessions` row carrying
`username`, `email`, `user_type` and `provider_id`. `traffic_logger.lua` runs in
the log phase of the very same request and never looks at it.

## Evidence

```
$ psql -c "SELECT count(DISTINCT auth_user) FROM traffic_logs WHERE auth_user IS NOT NULL;"
 0
```

`auth_user` appears only on the read path:

```
$ grep -rn "auth_user" backend/app/api/routes/ backend/app/schemas/
backend/app/api/routes/traffic.py:116:   "auth_user": log.auth_user,
backend/app/schemas/traffic.py:35:       auth_user: Optional[str]
```

The Lua log payload has no identity field at all — `client_ip`, `method`, `uri`,
`query_string`, `host`, `user_agent`, `referer`, status/timing/bytes/ssl, and
nothing else (`proxy/lua/traffic_logger.lua`).

Meanwhile `auth_wall.lua` already resolves a validated session per request:

```lua
local COOKIE_NAME = "gw_auth_session"
-- signed cookie: {session_id}.{signature}, session_id is 64 chars
```

## Root cause

The column was modelled for a feature that was never finished on the Lua side.
Because `auth_user` is nullable and only read, nothing fails — it just stays
empty.

## Impact

- No per-user analytics, on any host, even the ones sitting behind an auth wall
  where the user is positively identified.
- Threat attribution and audit are IP-only. Behind CGNAT or a shared office IP,
  several people are indistinguishable; and until
  [the real-IP fix](#) landed, everyone behind a CDN collapsed into a handful of
  edge addresses.
- "Unique visitors" cannot be reported at all.

## Recommended fix

**Authenticated hosts (accurate, no privacy trade-off — the user has already
identified themselves):** have `auth_wall.lua` stash the resolved username in
`ngx.ctx` during the access phase, and have `traffic_logger.lua` send it as
`auth_user`. Accept and persist it in the internal log endpoint.

**Public hosts** need a different mechanism, and it is a policy decision rather
than a technical one — a persistent first-party identifier is a consent question
in the UK/EU, and this proxy fronts other people's sites. Model it as a per-host
opt-in (`visitor_tracking_enabled`, default off) rather than a global default, so
the choice stays with whoever owns each site.

Note that a visitor ID identifies a *browser*, not a person, and that neither
mechanism counts humans — a large share of requests are bots, so bot
classification (from `user_agent` and honeypot hits) has to come before "unique
visitors" means anything.
