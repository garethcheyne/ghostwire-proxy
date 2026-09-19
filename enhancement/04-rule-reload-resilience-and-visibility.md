# 04 — Silent WAF/rate-limit/GeoIP rule reload failures

**Severity:** Medium
**Status:** **Not started** (2026-09-09) — see [README](README.md#not-started).
**Answers:** "not being able to see [the] reason why things may not work"

## TL;DR

Every rule type nginx enforces (WAF rules, blocked IPs, GeoIP rules, rate limits, trusted IPs,
honeypot traps) is loaded from the API into an nginx shared dict on a 60s timer, cached for
120s. Background reloads to `ghostwire-proxy-api` failed roughly **29,000 times** in the
current log window — mostly a recurring DNS resolution blip, plus at least one full API outage
where every rule type failed to reload simultaneously — and none of it is visible anywhere in
the admin UI. An admin has no way to tell, short of reading raw container logs, that
enforcement briefly went stale or that a specific host's DNS is flaky.

## Evidence

```
$ docker exec ghostwire-proxy-nginx sh -c "grep -oE '\[error\].*' /var/log/nginx/error.log | sed -E 's/\*[0-9]+/*N/' | sort | uniq -c | sort -rn"
  15103  [lua] init.lua:107: load_waf_rules(): Failed to fetch WAF rules from API:
           ghostwire-proxy-api could not be resolved (3: Host not found)
  13502  [lua] init.lua:149: load_blocked_ips(): Failed to fetch blocked IPs:
           ghostwire-proxy-api could not be resolved (3: Host not found)
    106  [lua] init.lua:269: load_honeypot_traps(): Failed to fetch honeypot traps: connection refused
    106  [lua] init.lua:239: load_trusted_ips(): Failed to fetch trusted IPs: connection refused
    106  [lua] init.lua:209: load_rate_limit_rules(): Failed to fetch rate limit rules: connection refused
    106  [lua] init.lua:179: load_geoip_rules(): Failed to fetch GeoIP rules: connection refused
    106  [lua] init.lua:149: load_blocked_ips(): Failed to fetch blocked IPs: connection refused
    106  [lua] init.lua:107: load_waf_rules(): Failed to fetch WAF rules from API: connection refused
```

The "could not be resolved" pattern (28,664 occurrences total across WAF+blocked-IPs alone)
recurs in tight clusters throughout the log, e.g. two hits 5 minutes apart at 01:10:45 and
01:15:46 — consistent with intermittent Docker embedded-DNS (`127.0.0.11`) resolution blips
rather than a sustained outage. The "connection refused" cluster (exactly 106 hits across
*every* rule type at once) is different in character — it's every `load_*` function failing
together, consistent with the `ghostwire-proxy-api` container being genuinely down/restarting
for a short window (there's a `ghostwire-watchtower` container in the fleet that
auto-updates images, which is a plausible trigger).

## Root cause

`proxy/lua/init.lua` fetches all six rule types via `resty.http`
(`load_waf_rules`, `load_blocked_ips`, `load_geoip_rules`, `load_rate_limit_rules`,
`load_trusted_ips`, `load_honeypot_traps`, all following the same pattern, e.g.
`init.lua:92-131`), each independently, on a worker timer calling
`reload_all_rules()` (`init.lua:284-291`) every `rule_reload_interval` = 60s
(`init.lua:23`). Each fetch:

- Resolves `ghostwire-proxy-api` via the nginx `resolver` directive
  (`proxy/nginx.conf:116`: `resolver 127.0.0.11 8.8.8.8 8.8.4.4 valid=300s ipv6=off;`) — a
  transient Docker DNS hiccup here fails the whole fetch for that cycle.
- On failure, just `ngx.log(ngx.ERR, ...)` and returns `false` — the *previous* successful
  fetch's data stays cached in the shared dict for `rule_reload_interval * 2` = 120s
  (e.g. `init.lua:123`), so a single missed cycle is harmless. But there's no tracking of
  *consecutive* failures, no metric, and no alerting — if DNS or the API stays unreachable for
  longer than 120s, the shared-dict cache simply expires and `get_waf_rules()` /
  `get_blocked_ips()` / etc. start returning `nil`, at which point the Lua modules'
  "no rules loaded" fallback behavior kicks in silently (e.g. `waf.lua:28-30`: `if not
  db_rules or #db_rules == 0 then return true, nil end` — WAF checks pass everything through
  when rules aren't loaded, which is fail-open for enforcement but fail-silent for
  visibility).
- Nothing in this whole chain reports state back to the API/DB, so there's no way for the
  admin UI to show "WAF rules last successfully synced 3 minutes ago" or similar.

## Impact

- During any reload gap longer than 120s, WAF/rate-limiting/GeoIP/honeypot enforcement quietly
  goes idle (fail-open) with zero indication in the UI that this happened — a security-relevant
  blind spot for a tool whose whole purpose is that enforcement.
- Troubleshooting "why isn't X being blocked/allowed right now" currently requires shelling
  into the nginx container and grepping raw logs, which isn't a reasonable expectation for
  day-to-day operation.

## Recommended fix

1. **Track last-successful-reload timestamps** per rule type in the shared dict (e.g.
   `config_cache:set("waf_rules_synced_at", ngx.time())` alongside each successful `set()`),
   and expose them via a small `/api/internal/*` style endpoint or a dedicated nginx `/status`
   Lua endpoint the API can poll and surface on the System/Dashboard page (e.g. "WAF rules:
   synced 12s ago", "Rate limits: **stale — last synced 4m ago**").
2. **Add a repeated-failure counter** per rule type; after N consecutive failures, log at
   `ngx.CRIT` (or push a notification via the existing `push_service` used for cert-expiry
   notifications) so a sustained outage is loud, not just noisy.
3. Consider **retrying within the same timer tick** (a couple of quick retries with backoff)
   for the DNS-blip case specifically, since `127.0.0.11` hiccups are usually resolved within
   a second or two — this alone would likely eliminate most of the 28,664 "could not be
   resolved" log lines without meaningfully increasing staleness.
4. Longer-term: consider having the API push rule updates (e.g. via a lightweight pub/sub over
   the existing Redis instance) instead of nginx polling every 60s — would reduce both the
   log volume and the worst-case staleness window.
