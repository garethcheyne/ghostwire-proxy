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

-- Skip traffic logging for trusted IPs
local function get_raw_client_ip()
    local xff = ngx.var.http_x_forwarded_for
    if xff then
        local first_ip = xff:match("^([^,]+)")
        if first_ip then return first_ip:gsub("^%s*(.-)%s*$", "%1") end
    end
    return ngx.var.http_x_real_ip or ngx.var.remote_addr
end

if init.is_trusted_ip(get_raw_client_ip()) then
    return
end

local http = require "resty.http"
local geoip = require "geoip"

-- Get real client IP (check X-Forwarded-For, X-Real-IP, then fall back to remote_addr)
local function get_client_ip()
    local xff = ngx.var.http_x_forwarded_for
    if xff then
        -- X-Forwarded-For can contain multiple IPs, get the first (original client)
        local first_ip = xff:match("^([^,]+)")
        if first_ip then
            return first_ip:gsub("^%s*(.-)%s*$", "%1")  -- trim whitespace
        end
    end

    local real_ip = ngx.var.http_x_real_ip
    if real_ip then
        return real_ip
    end

    return ngx.var.remote_addr
end

local log_data = {
    -- Request info
    timestamp = ngx.time(),
    client_ip = get_client_ip(),
    method = ngx.var.request_method,
    uri = ngx.var.uri,
    query_string = ngx.var.query_string,
    host = ngx.var.host,
    user_agent = ngx.var.http_user_agent,
    referer = ngx.var.http_referer,

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
    end

    -- Return connection to pool
    httpc:set_keepalive(60000, 10)
end)
