# 03 — Traffic logger corrupts its own HTTP keepalive pool

**Severity:** High
**Status:** **Done** (2026-09-09) — see [README](README.md#done).
**Answers:** "not being able to see [why the] webtraffic view [of] the proxy [isn't complete]"

## TL;DR

`proxy/lua/traffic_logger.lua` posts every request's log entry to the API using the
low-level `resty.http` `request()` call, then returns the socket to the keepalive pool
*without reading the response body*. The next request that reuses that pooled connection
reads the leftover, unread body bytes as if they were the start of a fresh HTTP response,
which breaks the status-line parser. The traffic log POST for that request is then dropped.
This has failed **~5,455 times** in the current log window and directly produces gaps in the
web traffic view.

## Evidence

```
$ docker exec ghostwire-proxy-nginx sh -c "grep -c 'traffic_logger.lua:148' /var/log/nginx/error.log"
[error] traffic_logger.lua:148: Failed to log traffic:
  couldn't parse HTTP version from response status line: {"status":"logged"}HTTP/1.1 200 OK
```
— 4,062 occurrences of exactly this message, plus 1,158 timeouts and 235 connection-refused
at the same call site (`traffic_logger.lua:132`/`148`).

The literal string in the error — `{"status":"logged"}HTTP/1.1 200 OK` — is the smoking gun:
`{"status":"logged"}` is the *previous* response's JSON body from
`/api/internal/traffic/log`, still sitting unread in the socket buffer, immediately followed
by the *next* response's real status line (`HTTP/1.1 200 OK`). The HTTP parser sees them
concatenated and fails.

## Root cause

`proxy/lua/traffic_logger.lua:136-152`:

```lua
local res, err = httpc:request({
    method = "POST",
    path = "/api/internal/traffic/log",
    body = cjson.encode(log_data),
    headers = { ... }
})

if not res then
    ngx.log(ngx.ERR, "Failed to log traffic: ", err)
end

-- Return connection to pool
httpc:set_keepalive(60000, 10)
```

`lua-resty-http`'s low-level `request()` (as opposed to `request_uri()`) returns as soon as
the response *headers* are parsed — it does **not** read the body for you. The body has to be
explicitly consumed via `res.body`, `res:read_body()`, or by streaming
`res.body_reader`, before the connection can safely be reused. This code does none of that:
it checks `res` for truthiness (to log an error) but never touches `res.body`, then
immediately calls `set_keepalive()`, handing a connection with an unread response body back
to the `"traffic_logger"` pool (`pool_size = 10`, so this corrupts up to 10 concurrent
connections). The very next `ngx.timer` that pulls that same connection out of the pool
starts its request, gets a response, and the parser chokes on the leftover bytes from the
prior response.

This is a well-known footgun with `lua-resty-http`'s low-level API — the library's own docs
call out that you must drain the body (or use `request_uri()`, which does it for you) before
`set_keepalive()`.

## Impact

- Any request whose traffic-log POST lands on a "poisoned" pooled connection silently fails
  to log — the request itself is proxied fine (this code runs in `log_by_lua_file`, after the
  response is already sent to the client), so end users see nothing wrong, but that request is
  simply missing from the Traffic/Analytics dashboards. This matches "not being able to see
  [complete] web traffic" — the data isn't wrong, it's incomplete, which is a harder class of
  bug to notice than an outright error.
- Because the failure is self-perpetuating within a pool (a poisoned connection stays poisoned
  until it's finally evicted/closed), failures tend to cluster in bursts rather than spread
  evenly, which matches the log pattern.

## Recommended fix

Simplest, lowest-risk fix — switch to the high-level `request_uri()` API, which handles body
reading and connection reuse safety for you, and matches what `init.lua`'s rule-loading
functions already do successfully elsewhere in this codebase:

```lua
local res, err = httpc:request_uri(api_base .. "/api/internal/traffic/log", {
    method = "POST",
    body = cjson.encode(log_data),
    headers = {
        ["Content-Type"] = "application/json",
        ["Host"] = "ghostwire-proxy-api",
        ["X-Internal-Auth"] = init.config.internal_auth_token,
    },
    keepalive_timeout = 60000,
    keepalive_pool = 10,
})
```

If the manual `connect()`-then-`request()` two-step (with the raw DNS-resolver fallback) is
still wanted to keep the explicit Docker-DNS retry logic, that's fine — just add
`local body = res.body` (or `res:read_body()`) immediately after the `request()` call,
*before* the `set_keepalive()` at the bottom, so the socket is guaranteed drained either way:

```lua
local res, err = httpc:request({ ... })
if res then
    local _ = res.body  -- drain the body so the connection is safe to reuse
end
...
httpc:set_keepalive(60000, 10)
```

Either fix should be verified by watching `traffic_logger.lua:148` disappear from
`error.log` after a reload, and by spot-checking that the Traffic dashboard's request counts
for a known time window now match nginx's own `access.log` line count for the same window.
