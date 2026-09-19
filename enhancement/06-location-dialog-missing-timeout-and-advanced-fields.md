# 06 — Add/Edit Location dialog has no fields for per-location timeouts or advanced config

**Severity:** High
**Status:** **Done** (2026-09-09) — see [README](README.md#done).
**Answers:** "why is ghostwire proxy timing out [for wingman.err403.com]" / "the UI in ghostwire is not wired up properly then"

## TL;DR

The backend fully supports per-location `proxy_connect_timeout` / `proxy_send_timeout` /
`proxy_read_timeout` and a per-location `advanced_config` — model, API, and the nginx
generator all handle them correctly, rendering each into that location's own `location {}`
block. But the **Add/Edit Location dialog in the frontend never renders inputs for any of
them.** An admin trying to raise `/api`'s timeouts (or add any custom directive to a specific
location) has no UI control to do it with — the only "Advanced" box anywhere on the page
belongs to the *host* dialog, and the generator deliberately renders that into the default
`/` location, not the location the admin actually meant to change.

This is exactly what happened on `wingman.err403.com`: someone tried to raise `/api`'s
60s timeout to handle slow LLM responses (gpt-5.5 reasoning-model calls routinely exceed 60s),
had no field to do it on the `/api` location, and pasted a hand-written
`location /api/ { ... }` snippet into the host-level Advanced box instead. It rendered as a
dead, unreachable nested location inside `location /` (which proxies to the *web app*, port
3120, not the API on 3200) — never took effect — and `/api/chat` kept timing out at the
original 60s.

## Evidence

**Production impact** — `wingman.err403.com`, `/var/log/nginx/error.log` in
`ghostwire-proxy-nginx`, repeating on a clean 60s cadence:

```
2026/09/08 08:16:18 [warn]  ... POST /api/chat HTTP/2.0 ...
2026/09/08 08:17:18 [error] ... upstream timed out (110: Operation timed out) while reading
  response header from upstream, ... upstream: "http://192.168.0.13:3200/api/chat"
```
(also 04:04, 04:11, 04:19 the same day, and going back to Aug 25 / Sep 2 / Sep 3 — this has
been happening for weeks.) `wingman-proxy`'s own logs show `[copilot-client] gpt-5.5 →
/responses` around the same timestamps — a reasoning model whose first-token latency
routinely exceeds nginx's 60s `proxy_read_timeout`.

**The broken config that resulted**, `conf.d/proxy-hosts/b96b9417-….conf`:

```nginx
location /api {                              # <- real handler for /api/chat, still 60s
    proxy_pass http://192.168.0.13:3200;
    ...
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}

location / {                                  # <- proxies to the WEB APP, port 3120
    proxy_pass http://192.168.0.13:3120;
    ...
    location /api/ {                          # <- dead: nginx never reaches this. /api
        proxy_read_timeout    300s;           #    (above) already wins the prefix match
        proxy_send_timeout    300s;           #    for every /api/* request, so this nested
        client_max_body_size   25m;           #    block is unreachable regardless of its
        proxy_buffering        off;           #    contents.
        # ... your existing proxy_pass        # <- and it was never finished either
    }
}
```

**Backend already supports this correctly** — `backend/app/models/proxy_host.py`,
`ProxyLocation`:

```python
proxy_connect_timeout = Column(Integer, default=60, nullable=False)
proxy_send_timeout    = Column(Integer, default=60, nullable=False)
proxy_read_timeout    = Column(Integer, default=60, nullable=False)
# Custom nginx directives for this location
advanced_config       = Column(Text, nullable=True)
```

`backend/app/services/openresty_service.py`, `_generate_location_block()`:

```python
lines.append(f"{indent}    proxy_connect_timeout {location.proxy_connect_timeout}s;")
lines.append(f"{indent}    proxy_send_timeout {location.proxy_send_timeout}s;")
lines.append(f"{indent}    proxy_read_timeout {location.proxy_read_timeout}s;")

# Advanced config for this location
if location.advanced_config:
    ...
    for line in location.advanced_config.strip().split("\n"):
```
— this renders correctly, into the *location's own* block, not the default one. The
generator is not the bug.

**Frontend gap** — `frontend/src/app/(dashboard)/dashboard/proxy-hosts/page.tsx`:

- `LocationFormData` (lines 81-98) and `defaultLocationData` (133-148) both carry
  `proxy_connect_timeout` / `proxy_send_timeout` / `proxy_read_timeout` / `advanced_config`.
- `handleEditLocation` (446-466) correctly *loads* an existing location's current values
  into form state (460-463) — so the data round-trips fine on save, it's just invisible.
- The actual "Add/Edit Location" dialog JSX (1430-1580) renders inputs for: path, priority,
  match type, forward host/port, websockets toggle, cache toggle, rate-limit toggle — **and
  nothing else.** No timeout inputs, no advanced-config textarea, no tabs at all.
- The only "Advanced" tab in the whole file (738-741, 814, 1365-1391) is on the **Proxy
  Host** dialog, and writes to `host.advanced_config` / `host.server_advanced_config` —
  fields the generator (correctly, by design — see `_generate_default_location`,
  openresty_service.py:256-260) renders into the default `/` location only.

## Root cause

Frontend/backend drift: the `ProxyLocation` model grew per-location timeout and
advanced-config fields at some point (both are fully wired through the API and the config
generator), but the Location dialog component was never updated to expose them. The only
advanced-config affordance visible to an admin is the host-level one, which is a different
field with different, documented (in a code comment) rendering behavior. There's nothing
in the UI to signal that distinction — both dialogs are just called "Advanced" — so pasting
a location-specific fix into the host dialog is the natural mistake to make, not user error.

## Impact

- No admin can tune per-location timeouts, body-size-relevant directives, or any custom
  nginx directive for a specific location through the UI at all — for *any* proxy host, not
  just wingman. The only escape hatches are direct API calls or hand-editing generated conf
  files (which get overwritten on the next save/regenerate).
- The failure mode is silent and misleading: the save succeeds, no error is shown, and the
  resulting config is syntactically valid nginx (nested locations are legal), so nothing
  flags it as wrong. The only symptom is the original problem (timeouts) continuing to
  happen, which reads as "my fix didn't work" rather than "I edited the wrong field."
- Directly caused ongoing production failures on `wingman.err403.com` — any chat request
  using a slower/reasoning model has been failing with a proxy timeout for at least two
  weeks (Aug 25 → Sep 8 in the logs).

## Recommended fix

**Immediate, no code change** — set the real fields via the API directly for the affected
location(s):

```
PUT /api/proxy-hosts/{wingman_host_id}/locations/{api_location_id}
{
  "proxy_read_timeout": 300,
  "proxy_send_timeout": 300,
  "advanced_config": "client_max_body_size 25m;\nproxy_buffering off;"
}
```
then remove the stray nested-`location /api/` snippet from the host's own Advanced tab
(it's dead weight, but worth cleaning up so the next person doesn't assume it's live), and
trigger a config regenerate + `nginx -s reload`.

**Real fix** — add the missing fields to the Add/Edit Location dialog in
`frontend/src/app/(dashboard)/dashboard/proxy-hosts/page.tsx`:
- Three number inputs for `proxy_connect_timeout` / `proxy_send_timeout` /
  `proxy_read_timeout` (state already exists — `locationForm.proxy_*_timeout` — this is
  purely a rendering gap).
- A textarea for `advanced_config`, ideally labeled distinctly from the host-level one
  (e.g. "Advanced config (this location only)") so the two are never confused again.

Should be verified by editing a test location's timeouts through the UI, regenerating, and
confirming the values land inside that location's own `location {}` block (not the default
one) in the resulting conf file — same spot-check method used for
[03](03-traffic-logger-connection-pool-corruption.md).
