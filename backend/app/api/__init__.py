from fastapi import APIRouter
from app.api.routes import auth, users, proxy_hosts, certificates, access_lists, auth_walls, traffic, settings, setup, dns, internal, analytics, waf, firewalls, alerts, rate_limits, geoip, auth_portal, system, backup, presets, updates

router = APIRouter()

# Setup routes (no auth required)
router.include_router(setup.router, prefix="/setup", tags=["Setup"])

# Internal routes (no auth - called from nginx Lua)
router.include_router(internal.router, prefix="/internal", tags=["Internal"])

# Auth portal routes (no auth - public login pages)
router.include_router(auth_portal.router, prefix="/auth-portal", tags=["Auth Portal"])

# Include all route modules
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
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
