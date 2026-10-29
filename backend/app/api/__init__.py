from fastapi import APIRouter

from app.api.routes import (
    access_lists,
    alerts,
    analytics,
    api_keys,
    auth_portal,
    auth_walls,
    backup,
    certificates,
    config_tools,
    containers,
    dns,
    firewalls,
    geoip,
    honeypot,
    internal,
    internal_admin_mfa,
    known_ips,
    mcp,
    mfa,
    presets,
    proxy_hosts,
    rate_limits,
    reports,
    search,
    settings,
    setup,
    system,
    traffic,
    updates,
    users,
    waf,
)

router = APIRouter()

# Setup routes (no auth required)
router.include_router(setup.router, prefix="/setup", tags=["Setup"])

# Internal routes (no auth - called from nginx Lua)
router.include_router(internal.router, prefix="/internal", tags=["Internal"])
router.include_router(internal_admin_mfa.router, prefix="/internal/admin-mfa", tags=["Internal"])

# Auth portal routes (no auth - public login pages)
router.include_router(auth_portal.router, prefix="/auth-portal", tags=["Auth Portal"])

# Include all route modules
# Admin sign-in (/api/auth/*) is Better Auth in the admin UI; see frontend/src/lib/auth.ts.
router.include_router(mfa.router, prefix="/admin-mfa", tags=["Two-Factor Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(proxy_hosts.router, prefix="/proxy-hosts", tags=["Proxy Hosts"])
router.include_router(certificates.router, prefix="/certificates", tags=["Certificates"])
router.include_router(access_lists.router, prefix="/access-lists", tags=["Access Lists"])
router.include_router(auth_walls.router, prefix="/auth-walls", tags=["Auth Walls"])
router.include_router(traffic.router, prefix="/traffic", tags=["Traffic"])
router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
router.include_router(settings.router, prefix="/settings", tags=["Settings"])
router.include_router(dns.router, tags=["DNS"])
router.include_router(waf.router, prefix="/waf", tags=["WAF & Threats"])
router.include_router(firewalls.router, prefix="/firewalls", tags=["Firewalls"])
router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
router.include_router(rate_limits.router, prefix="/rate-limits", tags=["Rate Limits"])
router.include_router(geoip.router, prefix="/geoip", tags=["GeoIP"])
router.include_router(system.router, prefix="/system", tags=["System Monitor"])
router.include_router(backup.router, prefix="/backups", tags=["Backups"])
router.include_router(presets.router, prefix="/presets", tags=["Security Presets"])
router.include_router(updates.router, prefix="/updates", tags=["Updates"])
router.include_router(honeypot.router, prefix="/honeypot", tags=["Honeypot"])
router.include_router(search.router, prefix="/search", tags=["Search"])
router.include_router(known_ips.router, prefix="/known-ips", tags=["Known IPs"])
router.include_router(reports.router, prefix="/reports", tags=["Reports"])
router.include_router(containers.router, prefix="/containers", tags=["Container Security"])

# Scripts and AI agents: scoped API keys (session-only to manage), config tooling and MCP.
router.include_router(api_keys.router, prefix="/api-keys", tags=["API Keys"])
router.include_router(config_tools.router, prefix="/config", tags=["Config"])
router.include_router(config_tools.audit_router, prefix="/audit-logs", tags=["Audit Log"])
router.include_router(mcp.router, prefix="/mcp", tags=["MCP"])
