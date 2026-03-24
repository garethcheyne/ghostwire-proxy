-- Ghostwire Proxy - Honeypot Module
-- Serves fake endpoints to catch scanners and gather attacker intelligence

local _M = {}
local cjson = require "cjson.safe"
local init = require "init"
local block_page = require "block_page"

-- Fake response templates per trap type
local fake_pages = {
    wordpress = [[
<!DOCTYPE html>
<html>
<head><title>Log In &lsaquo; WordPress</title>
<style>body{background:#f1f1f1;font-family:-apple-system,sans-serif}
.login{width:320px;margin:100px auto;padding:26px 24px;background:#fff;border:1px solid #c3c4c7;box-shadow:0 1px 3px rgba(0,0,0,.04)}
h1{text-align:center;margin-bottom:24px}
input{width:100%;padding:8px;margin:6px 0;box-sizing:border-box;border:1px solid #8c8f94}
.button-primary{background:#2271b1;color:#fff;border:none;padding:10px;cursor:pointer}
</style></head>
<body><div class="login"><h1>WordPress</h1>
<form method="post"><p><label>Username<br><input type="text" name="log"></label></p>
<p><label>Password<br><input type="password" name="pwd"></label></p>
<p><input type="submit" class="button-primary" value="Log In"></p></form></div></body>
</html>]],

    phpmyadmin = [[
<!DOCTYPE html>
<html>
<head><title>phpMyAdmin</title>
<style>body{background:#f3f3f3;font-family:sans-serif}
.container{width:400px;margin:80px auto;background:#fff;padding:30px;border:1px solid #ddd}
h1{font-size:24px;color:#333}
input{width:100%;padding:8px;margin:6px 0;box-sizing:border-box;border:1px solid #ccc}
.btn{background:#4CAF50;color:#fff;border:none;padding:10px;width:100%;cursor:pointer}
</style></head>
<body><div class="container"><h1>phpMyAdmin</h1>
<form method="post"><p><label>Username<br><input name="pma_username"></label></p>
<p><label>Password<br><input type="password" name="pma_password"></label></p>
<p><select name="pma_servername"><option>localhost</option></select></p>
<p><input type="submit" class="btn" value="Go"></p></form></div></body>
</html>]],

    admin = [[
<!DOCTYPE html>
<html>
<head><title>Admin Panel - Login</title>
<style>body{background:#1a1a2e;color:#eee;font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh}
.panel{background:#16213e;padding:40px;border-radius:8px;width:360px}
h2{margin-top:0;color:#e94560}
input{width:100%;padding:10px;margin:8px 0;border:1px solid #0f3460;background:#1a1a2e;color:#eee;box-sizing:border-box}
.btn{background:#e94560;border:none;padding:12px;width:100%;color:#fff;cursor:pointer;border-radius:4px}
</style></head>
<body><div class="panel"><h2>Admin Login</h2>
<form method="post"><input name="username" placeholder="Username">
<input type="password" name="password" placeholder="Password">
<button class="btn">Sign In</button></form></div></body>
</html>]],

    api = [[{"error":"unauthorized","message":"Authentication required","status":401}]],

    generic = [[
<!DOCTYPE html>
<html>
<head><title>403 Forbidden</title>
<style>body{font-family:sans-serif;text-align:center;padding:60px}
h1{font-size:48px;color:#555}p{color:#777}</style></head>
<body><h1>403</h1><p>Forbidden</p></body>
</html>]],
}

-- Get the fake page content for a trap
local function get_response(trap)
    -- Use custom response body if set
    if trap.response_body and trap.response_body ~= "" then
        return trap.response_body
    end
    -- Fall back to template
    return fake_pages[trap.trap_type] or fake_pages.generic
end

-- Get content type for trap type
local function get_content_type(trap)
    if trap.trap_type == "api" then
        return "application/json"
    end
    return "text/html"
end

-- Log the honeypot hit to the API (non-blocking)
local function log_hit(trap, client_ip)
    local uri = ngx.var.uri or ""
    local user_agent = ngx.var.http_user_agent or ""
    local host = ngx.var.host or ""
    local referer = ngx.var.http_referer or ""
    local method = ngx.var.request_method or ""
    local request_body_data = nil

    -- Read POST body if available
    if method == "POST" or method == "PUT" then
        ngx.req.read_body()
        local body = ngx.req.get_body_data()
        if body then
            -- Truncate to 2KB for safety
            request_body_data = string.sub(body, 1, 2048)
        end
    end

    -- Collect request headers
    local headers = ngx.req.get_headers() or {}
    local safe_headers = {}
    for k, v in pairs(headers) do
        if type(v) == "string" then
            safe_headers[k] = v
        end
    end

    -- GeoIP lookup
    local country_code = nil
    local country_name = nil
    local geoip = require "geoip"
    local geo = geoip.lookup(client_ip)
    if geo then
        country_code = geo.country_code
        country_name = geo.country_name
    end

    local payload = cjson.encode({
        trap_id = trap.id,
        trap_path = trap.path,
        client_ip = client_ip,
        request_method = method,
        request_uri = uri,
        request_headers = safe_headers,
        request_body = request_body_data,
        user_agent = user_agent,
        host = host,
        referer = referer,
        country_code = country_code,
        country_name = country_name,
        auto_block = trap.auto_block,
        severity = trap.severity,
    })

    -- Fire and forget: POST to the API
    ngx.timer.at(0, function(premature)
        if premature then return end

        local http = require "resty.http"
        local httpc = http.new()
        httpc:set_timeout(5000)

        local res, err = httpc:request_uri(
            init.config.api_url .. "/api/internal/honeypot/hit",
            {
                method = "POST",
                body = payload,
                headers = {
                    ["Content-Type"] = "application/json",
                    ["X-Internal-Auth"] = init.config.internal_auth_token,
                },
            }
        )

        if not res then
            ngx.log(ngx.ERR, "Honeypot hit log failed: ", err)
        end
    end)
end

-- Check if the current request matches a honeypot trap
-- Called from waf.lua or directly in access phase
function _M.check(client_ip)
    local traps = init.get_honeypot_traps()
    if not traps or #traps == 0 then
        return false
    end

    local uri = ngx.var.uri or ""
    local host_id = ngx.var.proxy_host_id or ""

    for _, trap in ipairs(traps) do
        -- Only match traps that are global (no proxy_host_id) or assigned to this host
        if trap.proxy_host_id == nil or trap.proxy_host_id == host_id then
            -- Exact path match (case-insensitive) or prefix match for paths ending with /
            local trap_path = trap.path
            local matched = false

            if string.sub(trap_path, -1) == "/" then
                -- Prefix match for directory-style traps
                matched = (string.sub(string.lower(uri), 1, #trap_path) == string.lower(trap_path))
            else
                -- Exact match
                matched = (string.lower(uri) == string.lower(trap_path))
            end

            if matched then
                -- Log the hit
                log_hit(trap, client_ip)

                -- Serve the fake response
                local body = get_response(trap)
                local content_type = get_content_type(trap)

                ngx.status = trap.response_code or 200
                ngx.header["Content-Type"] = content_type
                ngx.header["Server"] = "Apache/2.4.41 (Ubuntu)"  -- Fake server header
                ngx.header["X-Powered-By"] = "PHP/7.4.3"  -- Fake to look real
                ngx.say(body)
                ngx.exit(ngx.status)
                return true
            end
        end
    end

    return false
end

return _M
