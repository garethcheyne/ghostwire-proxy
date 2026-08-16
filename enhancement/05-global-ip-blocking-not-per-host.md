# 05 — Automatic IP blocking is global, not per-host

**Severity:** Medium
**Answers:** "rules being global and not per host"

## TL;DR

Manually-authored WAF rules, rate limits, and GeoIP rules already fully support per-host
scoping — DB column, API filter, and a host-picker in the UI all exist and work today. The
actual gap is **automatic IP blocking** driven by threat thresholds: once a client IP trips a
threshold on *any* proxied host, it gets blocked on *every* proxied host, because the
`ThreatActor`/blocked-IP model has no host concept at all.

## What already works (checked, not a bug)

- `RateLimitRule.proxy_host_id` (`backend/app/models/rate_limit.py:12`) is nullable
  (`NULL` = global) and `rate_limit.lua:get_limits_for_host()` (`proxy/lua/rate_limit.lua:19-50`)
  correctly prefers a host-specific rule over the global one.
- `WafRule.proxy_host_id` (`backend/app/models/waf.py:25`) — same pattern, and
  `waf.lua:check_db_rules()` (`proxy/lua/waf.lua:36-37`) applies "global rules (no host) or
  rules matching this host" per request.
- `GeoipRule.proxy_host_id` (`backend/app/models/rate_limit.py:41`) — same pattern.
- The Rate Limits and WAF admin pages (`frontend/src/app/(dashboard)/dashboard/rate-limits/page.tsx`,
  `.../waf/page.tsx`) both fetch the host list and let you scope a rule to one or more specific
  hosts vs. "All hosts" — this is already a real, working feature, not something to build from
  scratch.

## The actual gap

`backend/app/models/waf.py:66-84` — `ThreatActor` (the table tracking `current_status`:
`monitored → warned → temp_blocked → perm_blocked → firewall_banned`, driven by
`ThreatThreshold` rules) is keyed **only** by `ip_address` (unique) — there is no
`proxy_host_id` column, nullable or otherwise.

`proxy/lua/waf.lua:9-22`:
```lua
local function is_ip_blocked(client_ip)
    local blocked = init.get_blocked_ips()
    if not blocked then return false end
    for _, entry in ipairs(blocked) do
        if entry.ip == client_ip then
            return true
        end
    end
    return false
end
```
This check runs before the per-host WAF rule matching, for **every** vhost, with no
`proxy_host_id` comparison available to make — the data behind it simply doesn't carry that
information. `ThreatEvent` (the underlying event log that feeds the threshold logic) *does*
have `proxy_host_id` (`waf.py:46`), so the "this IP misbehaved on this host" information exists
at the event level — it's just discarded once it's rolled up into the account-wide
`ThreatActor.current_status` / global blocklist.

## Impact

An IP address that gets flagged for scanning/abuse against one low-value host (say, a
personal blog) is automatically blocklisted against *every* other proxied host — including
unrelated production services — even if it never touched them. This is arguably a reasonable
default for a *shared* home/lab-scale deployment (an abusive IP is usually abusive everywhere),
but it means there is currently no way to configure per-host threat response even if an admin
wants one, and it can produce confusing false positives ("why is this IP blocked on host B, it
only ever hit host A?") with no per-host toggle to fix it.

## Recommended fix

1. Add `proxy_host_id` (nullable = global, matching the existing convention used by
   `RateLimitRule`/`WafRule`/`GeoipRule`) to `ThreatActor`, or — simpler, avoids ambiguity when
   one IP is scored differently per host — introduce a `ThreatActorHostStatus` join table
   keyed on `(ip_address, proxy_host_id)` so an IP can be `perm_blocked` on host A while still
   `monitored` on host B, with global still expressible as `proxy_host_id IS NULL`.
2. Update `ThreatThreshold` evaluation (wherever `ThreatEvent`s are rolled up into
   `ThreatActor.current_status` — check `app/services/threat_service.py`) to key off
   `(ip_address, proxy_host_id)` when the threshold is scoped to specific host(s), falling back
   to the existing global behavior when it isn't.
3. Update `waf.lua:is_ip_blocked()` and `init.lua:load_blocked_ips()`/`get_blocked_ips()` to
   carry `proxy_host_id` per blocked-IP entry (mirroring the existing `rule.proxy_host_id ==
   nil or rule.proxy_host_id == host_id` pattern already used for WAF rules in the same file)
   and check it the same way.
4. Add a host selector to the Threat Actors / blocklist UI so this is actually configurable,
   consistent with how WAF rules and rate limits already expose it.
5. Keep "block globally" as the default action for new threshold rules (least behavior change
   for existing deployments) and let per-host scoping be opt-in.
