-- Ghostwire Proxy - Access Control Module
-- IP whitelist/blacklist enforcement from database-backed access lists

local _M = {}
local cjson = require "cjson.safe"
local init = require "init"

-- Cache for access list entries (refreshed periodically)
local access_cache = ngx.shared.access_cache

-- Check if IP matches a CIDR range
local function ip_in_cidr(ip, cidr)
    local ip_parts = {ip:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")}
    if #ip_parts ~= 4 then return false end

    local cidr_ip, mask_bits = cidr:match("^(.+)/(%d+)$")
    if not cidr_ip then
        -- Exact IP match
        return ip == cidr
    end

    local cidr_parts = {cidr_ip:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")}
    if #cidr_parts ~= 4 then return false end

    mask_bits = tonumber(mask_bits)
    if not mask_bits or mask_bits < 0 or mask_bits > 32 then return false end

    local ip_num = 0
    local cidr_num = 0
    for i = 1, 4 do
        ip_num = ip_num * 256 + tonumber(ip_parts[i])
        cidr_num = cidr_num * 256 + tonumber(cidr_parts[i])
    end

    if mask_bits == 0 then return true end

    local mask = 0xFFFFFFFF - (2 ^ (32 - mask_bits) - 1)
    local ip_masked = math.floor(ip_num / (2 ^ (32 - mask_bits))) * (2 ^ (32 - mask_bits))
    local cidr_masked = math.floor(cidr_num / (2 ^ (32 - mask_bits))) * (2 ^ (32 - mask_bits))

    return ip_masked == cidr_masked
end

-- Check access for a given host
function _M.check_access(host)
    local client_ip = ngx.var.remote_addr

    -- Fetch access list config from API (cached)
    local cache_key = "acl:" .. (host or "default")
    local cached = access_cache and access_cache:get(cache_key)

    if cached then
        local acl = cjson.decode(cached)
        if acl then
            return _M.evaluate(client_ip, acl)
        end
    end

    -- Fetch from API in background if not cached
    ngx.timer.at(0, function()
        _M.refresh_cache(host)
    end)

    -- Default: allow (fail open if cache miss)
    return true
end

-- Evaluate IP against access list rules
function _M.evaluate(ip, acl)
    if not acl or not acl.entries or #acl.entries == 0 then
        return true
    end

    local mode = acl.mode or "whitelist"

    for _, entry in ipairs(acl.entries) do
        if ip_in_cidr(ip, entry.ip_or_cidr) then
            if entry.action == "allow" then
                return true
            else
                return false
            end
        end
    end

    -- Default action based on mode
    if mode == "whitelist" then
        return false  -- Not in whitelist = deny
    else
        return true  -- Not in blacklist = allow
    end
end

-- Refresh cache from API
function _M.refresh_cache(host)
    local http = require "resty.http"
    local httpc = http.new()

    local res, err = httpc:request_uri(init.config.api_url .. "/api/internal/access-lists", {
        method = "GET",
        headers = {
            ["Content-Type"] = "application/json",
        },
        query = host and ("host=" .. host) or nil,
    })

    if res and res.status == 200 then
        local data = cjson.decode(res.body)
        if data and access_cache then
            local cache_key = "acl:" .. (host or "default")
            access_cache:set(cache_key, res.body, 60)  -- Cache for 60 seconds
        end
    elseif err then
        ngx.log(ngx.ERR, "Failed to refresh access cache: ", err)
    end
end

-- Main access handler
function _M.access()
    local host = ngx.var.host
    local allowed = _M.check_access(host)

    if not allowed then
        ngx.status = 403
        ngx.header["Content-Type"] = "application/json"
        ngx.say(cjson.encode({
            error = "Forbidden",
            message = "Access denied by access control list",
        }))
        return ngx.exit(403)
    end
end

return _M
