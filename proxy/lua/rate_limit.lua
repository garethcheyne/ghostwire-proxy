-- Ghostwire Proxy - Rate Limiting Module
-- Database-driven rate limiting using shared dictionary

local _M = {}
local init = require "init"

local rate_limit_dict = ngx.shared.rate_limit

-- Default limits (used when no DB rules match)
local default_limits = {
    requests_per_second = 100,
    requests_per_minute = 1000,
    burst_size = 50,
    action = "reject",
}

-- Find rate limit config for a given host from DB rules
local function get_limits_for_host(host)
    local db_rules = init.get_rate_limit_rules()
    if not db_rules or #db_rules == 0 then
        return default_limits
    end

    -- Look for host-specific rule first, then global
    local global_rule = nil
    for _, rule in ipairs(db_rules) do
        if rule.proxy_host_id == nil then
            global_rule = rule
        end
        -- Host matching would require proxy_host_id lookup;
        -- for now use global rules
    end

    if global_rule then
        return {
            requests_per_second = global_rule.requests_per_second or default_limits.requests_per_second,
            requests_per_minute = global_rule.requests_per_minute or default_limits.requests_per_minute,
            burst_size = global_rule.burst_size or default_limits.burst_size,
            action = global_rule.action or default_limits.action,
        }
    end

    return default_limits
end

-- Check rate limit for current request
-- Returns: allowed (bool), remaining (int), reset_time (int)
function _M.check(key, limits)
    limits = limits or default_limits

    local now = ngx.time()
    local window_key = key .. ":" .. math.floor(now / 60)

    -- Get current count
    local count = rate_limit_dict:get(window_key) or 0

    local rpm = limits.requests_per_minute or default_limits.requests_per_minute
    if count >= rpm then
        return false, 0, 60 - (now % 60)
    end

    -- Increment counter
    local new_count, err = rate_limit_dict:incr(window_key, 1, 0, 120)
    if err then
        ngx.log(ngx.ERR, "Rate limit incr error: ", err)
        return true, rpm, 60
    end

    return true, rpm - new_count, 60 - (now % 60)
end

-- Access handler
function _M.access()
    local client_ip = ngx.var.remote_addr
    local host = ngx.var.host or "default"

    -- Get limits from database (or defaults)
    local limits = get_limits_for_host(host)

    -- Create composite key
    local key = host .. ":" .. client_ip

    local allowed, remaining, reset = _M.check(key, limits)

    -- Set rate limit headers
    ngx.header["X-RateLimit-Remaining"] = remaining
    ngx.header["X-RateLimit-Reset"] = reset

    if not allowed then
        local action = limits.action or "reject"
        if action == "log" then
            ngx.log(ngx.WARN, "Rate limit exceeded for ", client_ip, " on ", host, " (log-only)")
            return
        end

        ngx.status = 429
        ngx.header["Content-Type"] = "application/json"
        ngx.header["Retry-After"] = reset
        ngx.say('{"error":"Too Many Requests","message":"Rate limit exceeded","retry_after":' .. reset .. '}')
        return ngx.exit(429)
    end
end

-- Get current stats for an IP
function _M.get_stats(ip, host)
    host = host or "default"
    local now = ngx.time()
    local window_key = host .. ":" .. ip .. ":" .. math.floor(now / 60)

    return {
        current_count = rate_limit_dict:get(window_key) or 0,
        window_start = math.floor(now / 60) * 60,
    }
end

return _M
