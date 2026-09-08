-- Ghostwire Proxy - Traffic Logger Module
-- Logs request/response data to backend API
-- This file is called directly via log_by_lua_file

local cjson = require "cjson.safe"
local init = require "init"

-- Check if traffic logging is enabled
if not init.config.traffic_logging_enabled then
    return
end

-- Skip health check endpoints
if ngx.var.uri == "/health" or ngx.var.uri == "/nginx-status" then
    return
end

-- Skip ACME challenge requests
if string.sub(ngx.var.uri, 1, 28) == "/.well-known/acme-challenge/" then
    return
end

-- Skip traffic logging for trusted IPs. init.get_client_ip() returns the address
-- nginx's real_ip module validated, never a raw request header -- otherwise a
-- visitor could opt themselves out of logging by naming a trusted IP.
if init.is_trusted_ip(init.get_client_ip()) then
    return
end

local http = require "resty.http"
local geoip = require "geoip"

-- ngx.ctx is readable here (log phase) but not inside the ngx.timer callback
-- below, so the value has to be captured into log_data now.
local log_data = {
    -- Request info
    timestamp = ngx.time(),
    client_ip = init.get_client_ip(),
    method = ngx.var.request_method,
    uri = ngx.var.uri,
    query_string = ngx.var.query_string,
    host = ngx.var.host,
    user_agent = ngx.var.http_user_agent,
    referer = ngx.var.http_referer,

    -- Identity, when the host sits behind an auth wall and the session was
    -- validated this request (set by auth_wall.lua). nil for public traffic.
    auth_user = ngx.ctx.auth_user,

    -- Response info
    status_code = ngx.status,
    response_time_ms = (tonumber(ngx.var.request_time) or 0) * 1000,
    bytes_sent = tonumber(ngx.var.bytes_sent) or 0,
    bytes_received = tonumber(ngx.var.request_length) or 0,

    -- Upstream info
    upstream_addr = ngx.var.upstream_addr,
    upstream_response_time = ngx.var.upstream_response_time,

    -- SSL info
    ssl_protocol = ngx.var.ssl_protocol,
    ssl_cipher = ngx.var.ssl_cipher,
}

-- GeoIP lookup using Lua module
local geo = geoip.lookup(log_data.client_ip)
if geo then
    log_data.country_code = geo.country_code
    log_data.country_name = geo.country_name
end

-- Non-blocking POST to API
ngx.timer.at(0, function(premature)
    if premature then
        return
    end

    local httpc = http.new()
    httpc:set_timeout(5000)

    -- Connect using Docker's internal DNS resolver
    local ok, conn_err = httpc:connect("ghostwire-proxy-api", 8000, {
        pool = "traffic_logger",
        pool_size = 10
    })

    if not ok then
        -- Try with Docker DNS resolver explicitly
        local resolver = require "resty.dns.resolver"
        local r, err = resolver:new{
            nameservers = {"127.0.0.11"},  -- Docker's internal DNS
            retrans = 2,
            timeout = 2000,
        }

        if r then
            local answers, dns_err = r:query("ghostwire-proxy-api", { qtype = r.TYPE_A })
            if answers and not answers.errcode then
                for _, ans in ipairs(answers) do
                    if ans.address then
                        ok, conn_err = httpc:connect(ans.address, 8000)
                        if ok then
                            break
                        end
                    end
                end
            end
        end
    end

    if not ok then
        ngx.log(ngx.ERR, "Failed to connect for traffic log: ", conn_err or "unknown")
        return
    end

    local res, err = httpc:request({
        method = "POST",
        path = "/api/internal/traffic/log",
        body = cjson.encode(log_data),
        headers = {
            ["Content-Type"] = "application/json",
            ["Host"] = "ghostwire-proxy-api",
            ["X-Internal-Auth"] = init.config.internal_auth_token,
        }
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to log traffic: ", err)
        -- The socket state is unknown after a failed request, so discard it
        -- rather than hand a possibly-corrupted connection back to the pool.
        httpc:close()
        return
    end

    -- The low-level request() returns as soon as the response headers are
    -- parsed; it does NOT consume the body. The body must be drained before the
    -- connection is reusable, otherwise the next request to pull this socket off
    -- the pool reads these leftover bytes as its own status line and the log
    -- POST is dropped.
    local body, body_err = res:read_body()
    if not body then
        ngx.log(ngx.ERR, "Failed to read traffic log response: ", body_err or "unknown")
        httpc:close()
        return
    end

    if res.status ~= 200 then
        ngx.log(ngx.ERR, "Traffic log rejected (HTTP ", res.status, "): ", body)
    end

    -- Only a fully-drained connection is safe to reuse.
    httpc:set_keepalive(60000, 10)
end)
