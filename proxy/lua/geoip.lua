-- Ghostwire Proxy - GeoIP Module
-- Database-driven geographic IP lookup and blocking

local _M = {}
local cjson = require "cjson.safe"
local init = require "init"

-- Lookup country for IP
function _M.lookup(ip)
    if not init.config.geoip_enabled or not init.geoip_db then
        return nil
    end

    local ok, result = pcall(function()
        return init.geoip_db:lookup(ip)
    end)

    if ok and result then
        return {
            country_code = result.country and result.country.iso_code,
            country_name = result.country and result.country.names and result.country.names.en,
            continent_code = result.continent and result.continent.code,
        }
    end

    return nil
end

-- Check if IP's country is in blocklist
function _M.check_blocklist(ip, blocklist)
    local geo = _M.lookup(ip)
    if not geo or not geo.country_code then
        return true, nil -- Allow if can't determine country
    end

    for _, country in ipairs(blocklist) do
        if string.upper(country) == string.upper(geo.country_code) then
            return false, geo
        end
    end

    return true, geo
end

-- Check if IP's country is in allowlist
function _M.check_allowlist(ip, allowlist)
    local geo = _M.lookup(ip)
    if not geo or not geo.country_code then
        return false, nil -- Block if can't determine country when using allowlist
    end

    for _, country in ipairs(allowlist) do
        if string.upper(country) == string.upper(geo.country_code) then
            return true, geo
        end
    end

    return false, geo
end

-- Access handler - loads rules from database, checks against configured rules
function _M.access(rules)
    if not init.config.geoip_enabled then
        return
    end

    local client_ip = ngx.var.remote_addr
    local geo = _M.lookup(client_ip)

    if not geo then
        return -- Can't determine, allow
    end

    -- Store for logging
    ngx.var.geoip_country_code = geo.country_code or ""
    ngx.var.geoip_country_name = geo.country_name or ""

    -- If explicit rules passed (legacy), use those
    if rules then
        local allowed = true

        if rules.mode == "blocklist" and rules.countries then
            allowed, _ = _M.check_blocklist(client_ip, rules.countries)
        elseif rules.mode == "allowlist" and rules.countries then
            allowed, _ = _M.check_allowlist(client_ip, rules.countries)
        end

        if not allowed then
            _M.block_response(geo, rules.action)
            return
        end
    end

    -- Load rules from database (via shared dict)
    local db_rules = init.get_geoip_rules()
    if not db_rules or #db_rules == 0 then
        return
    end

    local host = ngx.var.host

    for _, rule in ipairs(db_rules) do
        -- Apply global rules (no proxy_host_id) or host-specific rules
        local applies = (rule.proxy_host_id == nil or rule.proxy_host_id == ngx.var.proxy_host_id)

        if applies then
            local allowed = true

            if rule.mode == "blocklist" and rule.countries then
                allowed, _ = _M.check_blocklist(client_ip, rule.countries)
            elseif rule.mode == "allowlist" and rule.countries then
                allowed, _ = _M.check_allowlist(client_ip, rule.countries)
            end

            if not allowed then
                _M.block_response(geo, rule.action)
                return
            end
        end
    end
end

-- Send block response based on action type
function _M.block_response(geo, action)
    action = action or "block"

    if action == "log" then
        -- Log only, don't block
        ngx.log(ngx.WARN, "GeoIP: would block ", ngx.var.remote_addr,
            " from ", geo.country_code, " (log-only mode)")
        return
    end

    ngx.status = 403
    ngx.header["Content-Type"] = "application/json"
    ngx.say(cjson.encode({
        error = "Forbidden",
        message = "Access from your country is not allowed",
        country = geo.country_code,
    }))
    return ngx.exit(403)
end

return _M
