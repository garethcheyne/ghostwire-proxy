-- Ghostwire Proxy - WAF Module
-- Database-driven Web Application Firewall with hardcoded fallback

local _M = {}
local cjson = require "cjson.safe"
local init = require "init"
local block_page = require "block_page"

-- Check if an IP is currently blocked
local function is_ip_blocked(client_ip)
    local blocked = init.get_blocked_ips()
    if not blocked then
        return false
    end

    for _, entry in ipairs(blocked) do
        if entry.ip == client_ip then
            return true
        end
    end
    return false
end

-- Check request against database-loaded WAF rules
-- Returns: allowed (bool), threat_info (table or nil)
local function check_db_rules(uri, args, user_agent)
    local db_rules = init.get_waf_rules()
    if not db_rules or #db_rules == 0 then
        return true, nil  -- No DB rules loaded
    end

    local host_id = ngx.var.proxy_host_id
    local request_data = uri .. "?" .. args

    for _, rule in ipairs(db_rules) do
        -- Only apply global rules (no host) or rules matching this host
        if rule.proxy_host_id == nil or rule.proxy_host_id == host_id then
            local target
            if rule.category == "scanner" then
                -- Scanner rules match against User-Agent (plain string)
                local ua_lower = string.lower(user_agent)
                if string.find(ua_lower, string.lower(rule.pattern), 1, true) then
                    return false, {
                        rule_id = rule.id,
                        rule_name = rule.name,
                        category = rule.category,
                        severity = rule.severity,
                        action = rule.action,
                        pattern = rule.pattern,
                        matched = user_agent,
                    }
                end
            elseif rule.category == "path_traversal" or rule.category == "probe" then
                target = uri
            else
                target = request_data
            end

            -- Regex match for non-scanner rules
            if target then
                local ok, match = pcall(ngx.re.match, target, rule.pattern, "ijo")
                if not ok then
                    ngx.log(ngx.ERR, "Invalid WAF rule regex [" .. rule.name .. "]: " .. tostring(match))
                elseif match then
                    return false, {
                        rule_id = rule.id,
                        rule_name = rule.name,
                        category = rule.category,
                        severity = rule.severity,
                        action = rule.action,
                        pattern = rule.pattern,
                        matched = target,
                    }
                end
            end
        end
    end

    return true, nil
end

-- Main check — DB-driven only. All rules are managed in the UI (/dashboard/waf).
function _M.check_request()
    if not init.config.waf_enabled then
        return true, nil
    end

    local uri = ngx.var.uri or ""
    local args = ngx.var.query_string or ""
    local user_agent = ngx.var.http_user_agent or ""
    local client_ip = init.get_client_ip()

    -- Skip all checks for trusted IPs
    if init.is_trusted_ip(client_ip) then
        return true, nil
    end

    -- Check blocked IPs first
    if is_ip_blocked(client_ip) then
        return false, {
            category = "blocked_ip",
            severity = "critical",
            action = "block",
            pattern = "IP blocklist",
            matched = client_ip,
        }
    end

    -- DB rules only. Empty DB = no WAF rules applied.
    return check_db_rules(uri, args, user_agent)
end

-- Log threat event to backend API
function _M.log_threat(threat_info)
    local http = require "resty.http"
    local httpc = http.new()
    local geoip = require "geoip"

    local client_ip = init.get_client_ip()
    local geo = geoip.lookup(client_ip)

    local body = cjson.encode({
        client_ip = client_ip,
        category = threat_info.category,
        severity = threat_info.severity,
        pattern = threat_info.rule_name or threat_info.pattern,
        matched_payload = threat_info.matched,
        request_method = ngx.var.request_method,
        request_uri = ngx.var.uri,
        request_headers = ngx.req.get_headers(),
        user_agent = ngx.var.http_user_agent,
        host = ngx.var.host,
        timestamp = ngx.time(),
        country_code = geo and geo.country_code or nil,
        country_name = geo and geo.country_name or nil,
        rule_id = threat_info.rule_id or nil,
    })

    -- Non-blocking log to API
    ngx.timer.at(0, function()
        local res, err = httpc:request_uri(init.config.api_url .. "/api/internal/threats/log", {
            method = "POST",
            body = body,
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Internal-Auth"] = init.config.internal_auth_token,
            },
        })
        if not res then
            ngx.log(ngx.ERR, "Failed to log threat: ", err)
        end
    end)
end

-- Main access handler
function _M.access()
    local client_ip = init.get_client_ip()

    -- Check honeypot traps FIRST (before WAF rules)
    -- Only if honeypot is enabled for this virtual host
    local honeypot_enabled = ngx.var.honeypot_enabled
    if honeypot_enabled == "1" then
        local honeypot_ok, honeypot = pcall(require, "honeypot")
        if honeypot_ok and honeypot then
            local trapped = honeypot.check(client_ip)
            if trapped then
                return  -- honeypot already sent response
            end
        end
    end

    local allowed, threat_info = _M.check_request()

    if not allowed then
        -- Always log the threat
        _M.log_threat(threat_info)

        -- Determine action: log-only rules don't block
        local action = threat_info.action or "block"
        if action == "log" then
            -- Log only, don't block the request
            return
        end

        -- Block the request with branded page
        return block_page.waf_block(threat_info)
    end
end

return _M
