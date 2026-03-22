-- Ghostwire Proxy - Lua Initialization
-- This file is loaded once when OpenResty starts (init_by_lua)

local _M = {}
local cjson = require "cjson.safe"

-- Version
_M.version = "1.0.1"

-- Shared dictionaries for cross-worker data
local waf_cache = ngx.shared.waf_cache
local config_cache = ngx.shared.config_cache
local threat_cache = ngx.shared.threat_cache

-- Configuration
_M.config = {
    api_url = os.getenv("API_URL") or "http://ghostwire-proxy-api:8000",
    waf_enabled = true,
    rate_limit_enabled = true,
    geoip_enabled = false,
    traffic_logging_enabled = true,
    rule_reload_interval = 300,  -- seconds between rule reloads from DB
}

-- ============================================================================
-- GeoIP Database Initialization
-- ============================================================================

local function init_geoip()
    local ok, geo = pcall(require, "resty.maxminddb")
    if ok then
        local geoip_path = "/data/geoip/GeoLite2-Country.mmdb"
        local file = io.open(geoip_path, "r")
        if file then
            file:close()
            local init_ok, err = pcall(geo.init, geoip_path)
            if init_ok then
                _M.geoip_db = geo
                _M.config.geoip_enabled = true
                ngx.log(ngx.INFO, "GeoIP database loaded: ", geoip_path)
            else
                ngx.log(ngx.WARN, "GeoIP init failed: ", err or "unknown error")
            end
        else
            ngx.log(ngx.WARN, "GeoIP database not found: ", geoip_path)
        end
    else
        ngx.log(ngx.WARN, "MaxMindDB module not available: ", geo)
    end
end

-- ============================================================================
-- Default WAF Patterns (fallback if API is unreachable)
-- ============================================================================

_M.default_waf_rules = {
    {
        id = "default-sqli-1", name = "SQLi - OR/AND injection", category = "sqli",
        pattern = "('|\")(\\s)*(or|and)(\\s)+(1|true|'|\")", severity = "high", action = "block",
    },
    {
        id = "default-sqli-2", name = "SQLi - UNION SELECT", category = "sqli",
        pattern = "union(\\s)+select", severity = "high", action = "block",
    },
    {
        id = "default-sqli-3", name = "SQLi - SELECT FROM", category = "sqli",
        pattern = "select(\\s)+.*from", severity = "high", action = "block",
    },
    {
        id = "default-sqli-4", name = "SQLi - INSERT INTO", category = "sqli",
        pattern = "insert(\\s)+into", severity = "high", action = "block",
    },
    {
        id = "default-sqli-5", name = "SQLi - DELETE FROM", category = "sqli",
        pattern = "delete(\\s)+from", severity = "high", action = "block",
    },
    {
        id = "default-sqli-6", name = "SQLi - DROP TABLE/DB", category = "sqli",
        pattern = "drop(\\s)+(table|database)", severity = "critical", action = "block",
    },
    {
        id = "default-sqli-7", name = "SQLi - EXEC call", category = "sqli",
        pattern = "exec(\\s)*\\(", severity = "high", action = "block",
    },
    {
        id = "default-sqli-8", name = "SQLi - EXECUTE call", category = "sqli",
        pattern = "execute(\\s)*\\(", severity = "high", action = "block",
    },
    {
        id = "default-sqli-9", name = "SQLi - Hex encoding", category = "sqli",
        pattern = "0x[0-9a-fA-F]+", severity = "medium", action = "log",
    },
    {
        id = "default-sqli-10", name = "SQLi - CHAR function", category = "sqli",
        pattern = "char\\([0-9]+\\)", severity = "high", action = "block",
    },
    {
        id = "default-xss-1", name = "XSS - Script tag", category = "xss",
        pattern = "<script[^>]*>", severity = "high", action = "block",
    },
    {
        id = "default-xss-2", name = "XSS - javascript: URI", category = "xss",
        pattern = "javascript:", severity = "high", action = "block",
    },
    {
        id = "default-xss-3", name = "XSS - Event handler", category = "xss",
        pattern = "on\\w+\\s*=", severity = "high", action = "block",
    },
    {
        id = "default-xss-4", name = "XSS - iframe", category = "xss",
        pattern = "<iframe", severity = "high", action = "block",
    },
    {
        id = "default-xss-5", name = "XSS - object tag", category = "xss",
        pattern = "<object", severity = "medium", action = "block",
    },
    {
        id = "default-xss-6", name = "XSS - embed tag", category = "xss",
        pattern = "<embed", severity = "medium", action = "block",
    },
    {
        id = "default-xss-7", name = "XSS - CSS expression", category = "xss",
        pattern = "expression\\s*\\(", severity = "high", action = "block",
    },
    {
        id = "default-xss-8", name = "XSS - vbscript: URI", category = "xss",
        pattern = "vbscript:", severity = "high", action = "block",
    },
    {
        id = "default-pt-1", name = "Path Traversal - forward slash", category = "path_traversal",
        pattern = "\\.\\./", severity = "high", action = "block",
    },
    {
        id = "default-pt-2", name = "Path Traversal - backslash", category = "path_traversal",
        pattern = "\\.\\.\\\\", severity = "high", action = "block",
    },
    {
        id = "default-rce-1", name = "RCE - Semicolon command", category = "rce",
        pattern = ";\\s*(ls|cat|wget|curl|bash|sh|nc|netcat)", severity = "critical", action = "block",
    },
    {
        id = "default-rce-2", name = "RCE - Pipe command", category = "rce",
        pattern = "\\|\\s*(ls|cat|wget|curl|bash|sh|nc|netcat)", severity = "critical", action = "block",
    },
    {
        id = "default-rce-3", name = "RCE - Backtick execution", category = "rce",
        pattern = "`[^`]*`", severity = "critical", action = "block",
    },
    {
        id = "default-rce-4", name = "RCE - Subshell execution", category = "rce",
        pattern = "\\$\\([^)]*\\)", severity = "critical", action = "block",
    },
}

-- Scanner signatures (matched by plain string in User-Agent)
_M.default_scanner_sigs = {
    "nikto", "sqlmap", "nmap", "masscan", "dirbuster",
    "gobuster", "wpscan", "acunetix", "nessus",
}

-- Legacy compatibility: build waf_patterns from defaults
_M.waf_patterns = {
    sqli = {}, xss = {}, path_traversal = {}, rce = {},
    scanner = _M.default_scanner_sigs,
}
for _, rule in ipairs(_M.default_waf_rules) do
    local cat = rule.category
    if _M.waf_patterns[cat] then
        table.insert(_M.waf_patterns[cat], rule.pattern)
    end
end

-- ============================================================================
-- Rule Loading from Backend API
-- ============================================================================

--- Fetch WAF rules from the backend API and store in shared dict.
-- Called from worker init timer. Returns true on success.
function _M.load_waf_rules()
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)

    local url = _M.config.api_url .. "/api/internal/waf/rules"
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = { ["Content-Type"] = "application/json" },
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to fetch WAF rules from API: ", err)
        return false
    end

    if res.status ~= 200 then
        ngx.log(ngx.ERR, "WAF rules API returned status: ", res.status)
        return false
    end

    local rules = cjson.decode(res.body)
    if not rules then
        ngx.log(ngx.ERR, "Failed to decode WAF rules JSON")
        return false
    end

    -- Store rules in shared dict as JSON
    local ok, store_err = waf_cache:set("waf_rules", res.body, _M.config.rule_reload_interval * 2)
    if not ok then
        ngx.log(ngx.ERR, "Failed to store WAF rules in shared dict: ", store_err)
        return false
    end

    ngx.log(ngx.INFO, "Loaded ", #rules, " WAF rules from database")
    return true
end

--- Fetch blocked IPs from the backend API and store in shared dict.
function _M.load_blocked_ips()
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)

    local url = _M.config.api_url .. "/api/internal/blocked-ips"
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = { ["Content-Type"] = "application/json" },
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to fetch blocked IPs: ", err)
        return false
    end

    if res.status == 200 then
        threat_cache:set("blocked_ips", res.body, _M.config.rule_reload_interval * 2)
        local ips = cjson.decode(res.body)
        ngx.log(ngx.INFO, "Loaded ", ips and #ips or 0, " blocked IPs from database")
        return true
    end

    return false
end

--- Fetch GeoIP rules from the backend API and store in shared dict.
function _M.load_geoip_rules()
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)

    local url = _M.config.api_url .. "/api/internal/geoip/rules"
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = { ["Content-Type"] = "application/json" },
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to fetch GeoIP rules: ", err)
        return false
    end

    if res.status == 200 then
        config_cache:set("geoip_rules", res.body, _M.config.rule_reload_interval * 2)
        local rules = cjson.decode(res.body)
        ngx.log(ngx.INFO, "Loaded ", rules and #rules or 0, " GeoIP rules from database")
        return true
    end

    return false
end

--- Fetch rate limit rules from the backend API and store in shared dict.
function _M.load_rate_limit_rules()
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)

    local url = _M.config.api_url .. "/api/internal/rate-limits"
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = { ["Content-Type"] = "application/json" },
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to fetch rate limit rules: ", err)
        return false
    end

    if res.status == 200 then
        config_cache:set("rate_limit_rules", res.body, _M.config.rule_reload_interval * 2)
        local rules = cjson.decode(res.body)
        ngx.log(ngx.INFO, "Loaded ", rules and #rules or 0, " rate limit rules from database")
        return true
    end

    return false
end

--- Fetch trusted IPs from the backend API and store in shared dict.
function _M.load_trusted_ips()
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)

    local url = _M.config.api_url .. "/api/internal/trusted-ips"
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = { ["Content-Type"] = "application/json" },
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to fetch trusted IPs: ", err)
        return false
    end

    if res.status == 200 then
        config_cache:set("trusted_ips", res.body, _M.config.rule_reload_interval * 2)
        local ips = cjson.decode(res.body)
        ngx.log(ngx.INFO, "Loaded ", ips and #ips or 0, " trusted IPs from database")
        return true
    end

    return false
end

--- Load all rules from the backend API. Called by worker timer.
function _M.reload_all_rules()
    _M.load_waf_rules()
    _M.load_blocked_ips()
    _M.load_geoip_rules()
    _M.load_rate_limit_rules()
    _M.load_trusted_ips()
end

--- Get WAF rules from shared dict (returns parsed table or nil).
function _M.get_waf_rules()
    local json = waf_cache and waf_cache:get("waf_rules")
    if json then
        return cjson.decode(json)
    end
    return nil
end

--- Get blocked IPs from shared dict.
function _M.get_blocked_ips()
    local json = threat_cache and threat_cache:get("blocked_ips")
    if json then
        return cjson.decode(json)
    end
    return nil
end

--- Get GeoIP rules from shared dict.
function _M.get_geoip_rules()
    local json = config_cache and config_cache:get("geoip_rules")
    if json then
        return cjson.decode(json)
    end
    return nil
end

--- Get rate limit rules from shared dict.
function _M.get_rate_limit_rules()
    local json = config_cache and config_cache:get("rate_limit_rules")
    if json then
        return cjson.decode(json)
    end
    return nil
end

--- Get trusted IPs from shared dict.
function _M.get_trusted_ips()
    local json = config_cache and config_cache:get("trusted_ips")
    if json then
        return cjson.decode(json)
    end
    return nil
end

--- Check if an IP is in the trusted IPs list.
--- Supports exact IP match and CIDR notation.
function _M.is_trusted_ip(ip)
    local trusted = _M.get_trusted_ips()
    if not trusted or #trusted == 0 then
        return false
    end
    for _, entry in ipairs(trusted) do
        if entry == ip then
            return true
        end
        -- CIDR match
        if string.find(entry, "/", 1, true) then
            local ok, cidr_match = pcall(function()
                local cidr_ip, cidr_bits = entry:match("^([%d%.]+)/(%d+)$")
                if not cidr_ip or not cidr_bits then return false end
                cidr_bits = tonumber(cidr_bits)
                local function ip_to_int(addr)
                    local o1, o2, o3, o4 = addr:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
                    if not o1 then return nil end
                    return o1 * 16777216 + o2 * 65536 + o3 * 256 + o4
                end
                local ip_int = ip_to_int(ip)
                local cidr_int = ip_to_int(cidr_ip)
                if not ip_int or not cidr_int then return false end
                local mask = math.floor(2^32 - 2^(32 - cidr_bits))
                local function band(a, b)
                    local result = 0
                    local bitval = 1
                    while a > 0 and b > 0 do
                        if a % 2 == 1 and b % 2 == 1 then result = result + bitval end
                        bitval = bitval * 2
                        a = math.floor(a / 2)
                        b = math.floor(b / 2)
                    end
                    return result
                end
                return band(ip_int, mask) == band(cidr_int, mask)
            end)
            if ok and cidr_match then return true end
        end
    end
    return false
end

-- ============================================================================
-- Startup Initialization (runs in init_by_lua phase)
-- ============================================================================

init_geoip()

ngx.log(ngx.INFO, "Ghostwire Proxy initialized v", _M.version,
    " (rules loaded by workers via timer)")

return _M
