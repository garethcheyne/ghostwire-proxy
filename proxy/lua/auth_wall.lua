-- Ghostwire Proxy - Auth Wall Module
-- Server-side session authentication for protected proxy hosts
-- This module runs in access_by_lua phase BEFORE proxy_pass - cannot be bypassed

local _M = {}
local cjson = require "cjson.safe"
local init = require "init"

-- Shared memory for session caching (30 second TTL for performance)
local auth_sessions = ngx.shared.auth_sessions

-- Constants
local COOKIE_NAME = "gw_auth_session"
local CACHE_TTL = 30          -- Local cache TTL in seconds
local SIGNATURE_LENGTH = 32   -- Must match backend SessionService.SIGNATURE_LENGTH

-- Paths that bypass auth (login portal)
local AUTH_PORTAL_PATHS = {
    "^/__auth/",              -- Auth portal static files
    "^/api/auth%-portal/",    -- Auth portal API endpoints
    "^/favicon%.ico$",        -- Favicon
    "^/robots%.txt$"          -- Robots
}


-- Check if path should bypass auth
local function is_auth_portal_path(uri)
    for _, pattern in ipairs(AUTH_PORTAL_PATHS) do
        if ngx.re.match(uri, pattern, "ijo") then
            return true
        end
    end
    return false
end


-- Get session cookie value
local function get_session_cookie()
    return ngx.var["cookie_" .. COOKIE_NAME]
end


-- Extract session ID and signature from signed cookie (format: session_id.signature)
local function extract_session_parts(cookie_value)
    if not cookie_value then
        return nil, nil
    end

    -- Cookie format: {session_id}.{signature}
    local dot_pos = string.find(cookie_value, "%.", -SIGNATURE_LENGTH - 2)
    if not dot_pos then
        return nil, nil
    end

    local session_id = string.sub(cookie_value, 1, dot_pos - 1)
    local signature = string.sub(cookie_value, dot_pos + 1)

    if #session_id ~= 64 or #signature ~= SIGNATURE_LENGTH then
        return nil, nil
    end

    return session_id, signature
end

-- Backwards compatible wrapper
local function extract_session_id(cookie_value)
    local session_id, _ = extract_session_parts(cookie_value)
    return session_id
end


-- Get cached session from shared memory
local function get_cached_session(cache_key)
    local cached = auth_sessions:get(cache_key)
    if not cached then
        return nil
    end
    return cjson.decode(cached)
end


-- Cache session in shared memory
local function cache_session(cache_key, session_data)
    local encoded = cjson.encode(session_data)
    auth_sessions:set(cache_key, encoded, CACHE_TTL)
end


-- Validate session against backend API
local function validate_session_api(cookie_value, auth_wall_id)
    -- Extract session_id and signature from cookie
    local session_id, signature = extract_session_parts(cookie_value)
    if not session_id or not signature then
        ngx.log(ngx.WARN, "Auth wall: invalid cookie format, cookie length: ", #cookie_value)
        return nil
    end

    ngx.log(ngx.INFO, "Auth wall: validating session_id: ", string.sub(session_id, 1, 16), "..., wall_id: ", auth_wall_id)

    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)  -- 5 second timeout

    local api_url = init.config.api_url .. "/api/internal/auth-wall/validate-session"
    ngx.log(ngx.INFO, "Auth wall: calling API at: ", api_url)

    local res, err = httpc:request_uri(api_url, {
        method = "POST",
        body = cjson.encode({
            session_id = session_id,
            auth_wall_id = auth_wall_id,
            signature = signature
        }),
        headers = {
            ["Content-Type"] = "application/json"
        }
    })

    if err then
        ngx.log(ngx.ERR, "Auth wall session validation failed: ", err)
        return nil
    end

    if res.status ~= 200 then
        ngx.log(ngx.WARN, "Auth wall session validation returned status: ", res.status, " body: ", res.body)
        return nil
    end

    local body = cjson.decode(res.body)
    if not body or not body.valid then
        ngx.log(ngx.WARN, "Auth wall session not valid, response: ", res.body)
        return nil
    end

    ngx.log(ngx.INFO, "Auth wall session validated successfully for: ", body.session and body.session.username or "unknown")

    return body.session
end


-- Validate session (with caching)
local function validate_session(cookie_value, auth_wall_id)
    if not cookie_value or not auth_wall_id then
        return nil
    end

    -- Extract session ID for cache key
    local session_id = extract_session_id(cookie_value)
    if not session_id then
        return nil
    end

    -- Check local cache first
    local cache_key = "session:" .. auth_wall_id .. ":" .. session_id
    local cached = get_cached_session(cache_key)
    if cached then
        -- Check if cached session is still valid
        if cached.expires_at and cached.expires_at > ngx.time() then
            return cached
        end
        -- Cached session expired, remove it
        auth_sessions:delete(cache_key)
    end

    -- Validate against backend API
    local session = validate_session_api(cookie_value, auth_wall_id)
    if not session then
        return nil
    end

    -- Cache the valid session
    cache_session(cache_key, session)

    return session
end


-- Update session activity (debounced - only every 60 seconds)
local function update_activity(session_id)
    local activity_key = "activity:" .. session_id
    local last_update = auth_sessions:get(activity_key)

    if last_update and (ngx.time() - last_update) < 60 then
        -- Skip if updated within last minute
        return
    end

    -- Mark as updated
    auth_sessions:set(activity_key, ngx.time(), 60)

    -- Fire async request to update activity
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(2000)

    local api_url = init.config.api_url .. "/api/internal/auth-wall/update-activity"

    -- Non-blocking request (we don't wait for response)
    ngx.timer.at(0, function()
        local res, err = httpc:request_uri(api_url, {
            method = "POST",
            body = cjson.encode({
                session_id = session_id
            }),
            headers = {
                ["Content-Type"] = "application/json"
            }
        })
        if err then
            ngx.log(ngx.WARN, "Failed to update session activity: ", err)
        end
    end)
end


-- Set auth headers for upstream service
local function set_auth_headers(session)
    ngx.req.set_header("X-Auth-User", session.username or "")
    ngx.req.set_header("X-Auth-Email", session.email or "")
    ngx.req.set_header("X-Auth-User-Id", session.user_id or "")
    ngx.req.set_header("X-Auth-Provider", session.user_type or "")
    ngx.req.set_header("X-Auth-Display-Name", session.display_name or session.username or "")

    -- Remove any spoofed auth headers from client
    ngx.req.clear_header("X-Original-Auth-User")
    ngx.req.clear_header("X-Original-Auth-Email")
end


-- Redirect to login page
local function redirect_to_login(auth_wall_id)
    local original_uri = ngx.var.request_uri
    local encoded_redirect = ngx.escape_uri(original_uri)
    local login_url = "/__auth/login?wall=" .. auth_wall_id .. "&redirect=" .. encoded_redirect

    return ngx.redirect(login_url, ngx.HTTP_MOVED_TEMPORARILY)
end


-- Request HTTP Basic Auth
local function request_basic_auth(realm)
    realm = realm or "Protected"
    ngx.header["WWW-Authenticate"] = 'Basic realm="' .. realm .. '"'
    ngx.status = 401
    ngx.header["Content-Type"] = "application/json"
    ngx.say('{"error":"Unauthorized","message":"Authentication required"}')
    return ngx.exit(401)
end


-- Validate basic auth against backend
local function validate_basic_auth(auth_wall_id)
    local auth_header = ngx.var.http_authorization
    if not auth_header then
        return nil
    end

    local encoded = string.match(auth_header, "Basic%s+(.+)")
    if not encoded then
        return nil
    end

    local decoded = ngx.decode_base64(encoded)
    if not decoded then
        return nil
    end

    local username, password = string.match(decoded, "([^:]+):(.+)")
    if not username or not password then
        return nil
    end

    -- Validate against backend API
    local http = require "resty.http"
    local httpc = http.new()
    httpc:set_timeout(5000)

    local api_url = init.config.api_url .. "/api/internal/auth-wall/validate-basic"

    local res, err = httpc:request_uri(api_url, {
        method = "POST",
        body = cjson.encode({
            auth_wall_id = auth_wall_id,
            username = username,
            password = password
        }),
        headers = {
            ["Content-Type"] = "application/json"
        }
    })

    if err then
        ngx.log(ngx.ERR, "Basic auth validation failed: ", err)
        return nil
    end

    if res.status ~= 200 then
        return nil
    end

    local body = cjson.decode(res.body)
    if body and body.valid then
        return body.session
    end

    return nil
end


-- Main access handler
-- Called from access_by_lua_file in nginx config
function _M.access()
    -- Get auth_wall_id from nginx variable (set in server block)
    local auth_wall_id = ngx.var.auth_wall_id

    -- If no auth wall configured, allow request
    if not auth_wall_id or auth_wall_id == "" then
        return
    end

    -- Allow auth portal paths to pass through
    local uri = ngx.var.uri
    if is_auth_portal_path(uri) then
        return
    end

    -- Get auth wall config (for auth_type)
    local auth_type = ngx.var.auth_wall_type or "multi"

    -- Handle HTTP Basic Auth
    if auth_type == "basic" then
        local session = validate_basic_auth(auth_wall_id)
        if session then
            set_auth_headers(session)
            return
        end
        return request_basic_auth(ngx.var.auth_wall_name or "Protected")
    end

    -- For form-based auth (multi, oauth, local), check session cookie
    local cookie_value = get_session_cookie()
    ngx.log(ngx.INFO, "Auth wall: checking session, cookie present: ", cookie_value and "yes" or "no")

    if cookie_value then
        ngx.log(ngx.INFO, "Auth wall: validating session for wall_id: ", auth_wall_id)
        local session = validate_session(cookie_value, auth_wall_id)
        if session then
            ngx.log(ngx.INFO, "Auth wall: session valid for user: ", session.username or "unknown")
            -- Valid session - set headers and continue
            set_auth_headers(session)

            -- Update activity asynchronously
            local session_id = extract_session_id(cookie_value)
            if session_id then
                update_activity(session_id)
            end

            return
        end
    end

    -- No valid session - redirect to login
    ngx.log(ngx.WARN, "Auth wall: no valid session, redirecting to login. Cookie was: ", cookie_value and "present" or "missing")
    return redirect_to_login(auth_wall_id)
end


-- Handle auth callback (called from location /__auth/callback)
function _M.callback()
    -- This is handled by the backend API now
    -- The frontend callback page will call the API and set the cookie
    return
end


-- Handle logout
function _M.logout()
    -- Clear local cache if we have a session
    local cookie_value = get_session_cookie()
    if cookie_value then
        local session_id = extract_session_id(cookie_value)
        local auth_wall_id = ngx.var.auth_wall_id

        if session_id and auth_wall_id then
            local cache_key = "session:" .. auth_wall_id .. ":" .. session_id
            auth_sessions:delete(cache_key)
        end
    end

    -- Backend will handle cookie clearing
    return
end


-- Invalidate session from cache (called when session is revoked)
function _M.invalidate_session(auth_wall_id, session_id)
    if auth_wall_id and session_id then
        local cache_key = "session:" .. auth_wall_id .. ":" .. session_id
        auth_sessions:delete(cache_key)
    end
end


return _M
