-- Ghostwire Proxy - Branded Block Page
-- Returns styled HTML block pages with incident reference numbers

local _M = {}
local logo_data = require "logo_data"

-- Generate a unique incident reference from timestamp + random
local function generate_incident_id()
    local t = ngx.now() * 1000
    local r = math.random(1000, 9999)
    return string.format("GW-%s-%04d", string.format("%012.0f", t), r)
end

-- Map category to human-friendly reason and description
local function get_reason_info(category, message)
    local info = {
        sqli           = { title = "SQL Injection Detected",           desc = "The request contained patterns that match known SQL injection techniques." },
        xss            = { title = "Cross-Site Scripting Detected",    desc = "The request contained patterns associated with cross-site scripting attacks." },
        rce            = { title = "Remote Code Execution Attempt",    desc = "The request contained patterns that could lead to unauthorized code execution." },
        path_traversal = { title = "Path Traversal Attempt",           desc = "The request attempted to access files outside the permitted directory." },
        scanner        = { title = "Automated Scanner Blocked",        desc = "Automated vulnerability scanning tools are not permitted." },
        protocol       = { title = "Protocol Violation Detected",      desc = "The request violated expected protocol standards." },
        blocked_ip     = { title = "IP Address Blocked",               desc = "Your IP address has been temporarily restricted due to suspicious activity." },
        rate_limit     = { title = "Rate Limit Exceeded",              desc = "Too many requests have been sent in a short period. Please wait and try again." },
        access_denied  = { title = "Access Denied",                    desc = "You do not have permission to access this resource." },
        geo_blocked    = { title = "Geographic Restriction",           desc = "Access from your region is not permitted by the site's security policy." },
    }
    local entry = info[category]
    if entry then return entry.title, entry.desc end
    return message or "Security Policy Violation", "The request was blocked by the web application firewall."
end

-- Logo image tag using base64-encoded PNG
local function get_logo_img()
    return '<img src="' .. logo_data.data_uri .. '" alt="Ghostwire" class="logo-img" width="56" height="56">'
end

-- Render the branded block page HTML
local function render_page(opts)
    local status_code = opts.status or 403
    local category = opts.category or "blocked"
    local reason_title, reason_desc = get_reason_info(category, opts.message)
    local incident_id = generate_incident_id()
    local client_ip = ngx.var.remote_addr or "unknown"
    local timestamp = ngx.cookie_time(ngx.time())
    local host = ngx.var.host or "unknown"
    local ray_id = string.format("%016x", ngx.crc32_long(incident_id .. client_ip .. ngx.now()))
    local retry_after = opts.retry_after

    -- Color theming per block type
    local accent = "#ef4444"
    local accent_rgb = "239,68,68"
    local accent_glow = "ef4444"
    local status_label = "BLOCKED"

    if status_code == 429 then
        accent = "#f59e0b"
        accent_rgb = "245,158,11"
        accent_glow = "f59e0b"
        status_label = "RATE LIMITED"
    elseif category == "geo_blocked" then
        accent = "#8b5cf6"
        accent_rgb = "139,92,246"
        accent_glow = "8b5cf6"
        status_label = "RESTRICTED"
    elseif category == "blocked_ip" then
        accent = "#f43f5e"
        accent_rgb = "244,63,94"
        accent_glow = "f43f5e"
        status_label = "BLOCKED"
    end

    local retry_html = ""
    if retry_after then
        retry_html = string.format([[
        <div class="retry">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <span>Retry in <strong>%d seconds</strong></span>
        </div>]], retry_after)
    end

    return string.format([[<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s | Ghostwire</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
@keyframes fadeIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%%,100%%{opacity:.4}50%%{opacity:.8}}
@keyframes float{0%%,100%%{transform:translateY(0)}50%%{transform:translateY(-6px)}}
@keyframes scan{0%%{top:-2px}100%%{top:calc(100%% + 2px)}}
body{
  min-height:100vh;display:flex;align-items:center;justify-content:center;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,sans-serif;
  background:#020817;color:#e2e8f0;padding:24px;
  background-image:
    radial-gradient(ellipse at top,rgba(%s,0.06) 0%%,transparent 60%%),
    radial-gradient(circle at 20%% 80%%,rgba(34,211,238,0.03) 0%%,transparent 40%%);
}
.page{max-width:520px;width:100%%;animation:fadeIn .5s ease-out}

.logo-row{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:32px}
.logo-ghost{animation:float 4s ease-in-out infinite;position:relative}
.logo-ghost::after{
  content:'';position:absolute;inset:-8px;border-radius:50%%;
  background:radial-gradient(circle,rgba(34,211,238,0.25) 0%%,transparent 70%%);
  z-index:-1;animation:pulse 3s ease-in-out infinite;
}
.logo-img{
  filter:brightness(0) saturate(100%%) invert(71%%) sepia(53%%) saturate(425%%) hue-rotate(162deg) brightness(95%%) contrast(92%%);
  display:block;
}
.logo-text{font-size:20px;font-weight:700;letter-spacing:-.3px}
.logo-text span{background:linear-gradient(135deg,#22d3ee,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}

.card{
  background:rgba(15,23,42,0.8);
  backdrop-filter:blur(12px);
  border:1px solid rgba(148,163,184,0.1);
  border-radius:16px;
  overflow:hidden;
  position:relative;
}
.card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,%s,transparent);
}

.status-bar{
  display:flex;align-items:center;gap:10px;
  padding:16px 24px;
  background:rgba(%s,0.06);
  border-bottom:1px solid rgba(148,163,184,0.08);
}
.status-dot{
  width:8px;height:8px;border-radius:50%%;
  background:%s;
  box-shadow:0 0 8px %s;
  animation:pulse 2s ease-in-out infinite;
}
.status-label{
  font-size:11px;font-weight:700;letter-spacing:1.5px;
  color:%s;text-transform:uppercase;
}
.status-code-pill{
  margin-left:auto;
  font-size:12px;font-weight:600;
  padding:3px 10px;border-radius:20px;
  background:rgba(%s,0.12);
  color:%s;
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
}

.main{padding:28px 24px}
.reason-title{font-size:22px;font-weight:700;color:#f1f5f9;margin-bottom:8px;line-height:1.3}
.reason-desc{font-size:14px;color:#94a3b8;line-height:1.6;margin-bottom:24px}

.details-grid{
  display:grid;gap:1px;
  background:rgba(148,163,184,0.06);
  border-radius:10px;
  overflow:hidden;
  border:1px solid rgba(148,163,184,0.08);
}
.detail-row{
  display:grid;grid-template-columns:120px 1fr;
  background:#0f172a;
}
.detail-row:first-child .detail-label,
.detail-row:first-child .detail-value{padding-top:14px}
.detail-row:last-child .detail-label,
.detail-row:last-child .detail-value{padding-bottom:14px}
.detail-label{
  padding:8px 16px;font-size:12px;font-weight:600;
  color:#64748b;text-transform:uppercase;letter-spacing:.5px;
  display:flex;align-items:center;
}
.detail-value{
  padding:8px 16px;font-size:13px;color:#cbd5e1;
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
  word-break:break-all;
  display:flex;align-items:center;
}

.retry{
  margin-top:16px;padding:12px 16px;
  background:rgba(245,158,11,0.08);
  border:1px solid rgba(245,158,11,0.2);
  border-radius:10px;
  color:#fbbf24;font-size:13px;
  display:flex;align-items:center;gap:10px;
}

.divider{
  height:1px;margin:0;
  background:linear-gradient(90deg,transparent,rgba(148,163,184,0.1),transparent);
}

.footer{
  padding:16px 24px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;
}
.footer-brand{display:flex;align-items:center;gap:8px}
.footer-logo{opacity:.5;filter:brightness(0) saturate(100%%) invert(71%%) sepia(53%%) saturate(425%%) hue-rotate(162deg) brightness(95%%) contrast(92%%)}
.footer-text{font-size:12px;color:#475569;font-weight:500}
.footer-ray{
  font-size:11px;color:#334155;
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
}

.help-text{
  text-align:center;margin-top:20px;font-size:12px;color:#475569;
}
.help-text a{color:#22d3ee;text-decoration:none}
.help-text a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="page">

  <div class="logo-row">
    <div class="logo-ghost">%s</div>
    <div class="logo-text"><span>Ghostwire</span></div>
  </div>

  <div class="card">
    <div class="status-bar">
      <div class="status-dot"></div>
      <div class="status-label">%s</div>
      <div class="status-code-pill">%d</div>
    </div>

    <div class="main">
      <div class="reason-title">%s</div>
      <div class="reason-desc">%s</div>
      %s

      <div class="details-grid">
        <div class="detail-row">
          <div class="detail-label">Incident</div>
          <div class="detail-value">%s</div>
        </div>
        <div class="detail-row">
          <div class="detail-label">Client IP</div>
          <div class="detail-value">%s</div>
        </div>
        <div class="detail-row">
          <div class="detail-label">Host</div>
          <div class="detail-value">%s</div>
        </div>
        <div class="detail-row">
          <div class="detail-label">Time</div>
          <div class="detail-value">%s</div>
        </div>
      </div>
    </div>

    <div class="divider"></div>

    <div class="footer">
      <div class="footer-brand">
        <img src="%s" alt="" class="footer-logo" width="18" height="18">
        <span class="footer-text">Protected by Ghostwire Proxy</span>
      </div>
      <span class="footer-ray">%s</span>
    </div>
  </div>

  <div class="help-text">
    If you believe this is an error, contact the site administrator with the incident ID above.
  </div>

</div>
</body>
</html>]],
        -- title
        reason_title,
        -- body bg radial gradient
        accent_rgb,
        -- card top border gradient
        accent,
        -- status bar bg
        accent_rgb,
        -- dot color, dot shadow
        accent, accent,
        -- status label color
        accent,
        -- pill bg, pill color
        accent_rgb, accent,
        -- ghost SVG logo
        -- ghost logo img
        get_logo_img(),
        -- status label, status code
        status_label, status_code,
        -- reason title, reason desc
        reason_title, reason_desc,
        -- retry section
        retry_html,
        -- details
        incident_id, client_ip, host, timestamp,
        -- footer logo
        logo_data.data_uri,
        -- ray id
        ray_id
    )
end

-- Send a WAF block page (403)
function _M.waf_block(threat_info)
    ngx.status = 403
    ngx.header["Content-Type"] = "text/html; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(render_page({
        status = 403,
        category = threat_info.category,
        message = threat_info.rule_name,
    }))
    return ngx.exit(403)
end

-- Send a rate limit page (429)
function _M.rate_limit_block(retry_after)
    ngx.status = 429
    ngx.header["Content-Type"] = "text/html; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.header["Retry-After"] = retry_after
    ngx.say(render_page({
        status = 429,
        category = "rate_limit",
        retry_after = retry_after,
    }))
    return ngx.exit(429)
end

-- Send an access denied page (403)
function _M.access_denied()
    ngx.status = 403
    ngx.header["Content-Type"] = "text/html; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(render_page({
        status = 403,
        category = "access_denied",
    }))
    return ngx.exit(403)
end

-- Send a geo block page (403)
function _M.geo_block(country_code)
    ngx.status = 403
    ngx.header["Content-Type"] = "text/html; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(render_page({
        status = 403,
        category = "geo_blocked",
        message = "Access from " .. (country_code or "your region") .. " is restricted",
    }))
    return ngx.exit(403)
end

return _M
