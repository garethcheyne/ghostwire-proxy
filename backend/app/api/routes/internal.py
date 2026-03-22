"""Internal API endpoints for nginx/Lua and updater integration."""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.core.database import get_db
from app.core.utils import generate_secure_token

logger = logging.getLogger(__name__)

# Internal auth token for updater service
# Generate a random token if not provided via environment
_env_token = os.environ.get("INTERNAL_AUTH_TOKEN", "")
if not _env_token:
    _env_token = generate_secure_token(48)
    logger.warning(
        "INTERNAL_AUTH_TOKEN not set in environment. Generated random token. "
        "For production, set INTERNAL_AUTH_TOKEN in your .env file."
    )
INTERNAL_AUTH_TOKEN = _env_token
from app.models.traffic_log import TrafficLog
from app.models.proxy_host import ProxyHost
from app.models.auth_wall import AuthWall, LocalAuthUser, AuthProvider, LdapConfig
from app.models.auth_wall_session import AuthWallSession
from app.services.session_service import SessionService
from app.schemas.auth_wall_session import (
    SessionValidateRequest,
    SessionValidateResponse,
    AuthWallConfigResponse,
    AuthWallConfigProvider,
)
from sqlalchemy import select

router = APIRouter()


class TrafficLogRequest(BaseModel):
    """Traffic log data from nginx Lua script."""
    timestamp: int  # Unix timestamp
    client_ip: str
    method: str
    uri: str
    query_string: Optional[str] = None
    host: str
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    status_code: int
    response_time_ms: float
    bytes_sent: int = 0
    bytes_received: int = 0
    upstream_addr: Optional[str] = None
    upstream_response_time: Optional[str] = None
    ssl_protocol: Optional[str] = None
    ssl_cipher: Optional[str] = None
    country_code: Optional[str] = None


@router.post("/traffic/log")
async def log_traffic(
    data: TrafficLogRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive traffic log from nginx Lua script."""
    # Find proxy host by domain
    result = await db.execute(select(ProxyHost))
    hosts = result.scalars().all()

    proxy_host_id = None
    for host in hosts:
        if data.host in host.domain_names:
            proxy_host_id = host.id
            break

    if not proxy_host_id:
        # Unknown host, skip logging
        return {"status": "skipped", "reason": "unknown host"}

    # Parse upstream response time
    upstream_time = None
    if data.upstream_response_time:
        try:
            # Can be comma-separated for multiple upstreams
            times = data.upstream_response_time.split(",")
            upstream_time = int(float(times[-1].strip()) * 1000)
        except (ValueError, IndexError):
            pass

    # Create traffic log entry
    log = TrafficLog(
        id=str(uuid.uuid4()),
        proxy_host_id=proxy_host_id,
        timestamp=datetime.fromtimestamp(data.timestamp, tz=timezone.utc),
        client_ip=data.client_ip,
        request_method=data.method,
        request_uri=data.uri,
        query_string=data.query_string,
        status=data.status_code,
        response_time=int(data.response_time_ms),
        bytes_sent=data.bytes_sent,
        bytes_received=data.bytes_received,
        upstream_addr=data.upstream_addr,
        upstream_response_time=upstream_time,
        ssl_protocol=data.ssl_protocol,
        ssl_cipher=data.ssl_cipher,
        user_agent=data.user_agent,
        referer=data.referer,
        country_code=data.country_code,
    )

    db.add(log)
    await db.commit()

    return {"status": "logged"}


class ThreatLogRequest(BaseModel):
    """Threat event data from nginx WAF Lua script."""
    client_ip: str
    category: str
    severity: str
    pattern: Optional[str] = None
    matched_payload: Optional[str] = None
    request_method: Optional[str] = None
    request_uri: Optional[str] = None
    request_headers: Optional[dict] = None
    user_agent: Optional[str] = None
    host: Optional[str] = None
    timestamp: Optional[int] = None


@router.post("/threats/log")
async def log_threat(
    data: ThreatLogRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive threat event from nginx WAF Lua script."""
    import json

    from app.services.threat_service import record_threat_event

    # Find proxy host by domain
    proxy_host_id = None
    if data.host:
        result = await db.execute(select(ProxyHost))
        hosts = result.scalars().all()
        for host in hosts:
            if data.host in host.domain_names:
                proxy_host_id = host.id
                break

    headers_json = json.dumps(data.request_headers) if data.request_headers else None

    await record_threat_event(
        db=db,
        client_ip=data.client_ip,
        category=data.category,
        severity=data.severity,
        action_taken="blocked",
        request_method=data.request_method,
        request_uri=data.request_uri,
        request_headers=headers_json,
        matched_payload=data.matched_payload,
        user_agent=data.user_agent,
        host=data.host,
        proxy_host_id=proxy_host_id,
        rule_name=data.pattern,
    )

    return {"status": "logged"}


# ============================================================================
# WAF / GeoIP / Blocklist Internal Endpoints (called by Lua)
# ============================================================================

@router.get("/waf/rules")
async def get_waf_rules(
    db: AsyncSession = Depends(get_db),
):
    """Return all enabled WAF rules for Lua to cache."""
    from app.models.waf import WafRule

    result = await db.execute(
        select(WafRule).where(WafRule.enabled == True, WafRule.is_lua == True)
    )
    rules = result.scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "pattern": r.pattern,
            "severity": r.severity,
            "action": r.action,
        }
        for r in rules
    ]


@router.get("/geoip/rules")
async def get_geoip_rules(
    db: AsyncSession = Depends(get_db),
):
    """Return all enabled GeoIP rules for Lua to cache."""
    from app.models.rate_limit import GeoipRule

    result = await db.execute(
        select(GeoipRule).where(GeoipRule.enabled == True)
    )
    rules = result.scalars().all()

    import json
    return [
        {
            "id": r.id,
            "proxy_host_id": r.proxy_host_id,
            "name": r.name,
            "mode": r.mode,
            "countries": json.loads(r.countries) if isinstance(r.countries, str) else r.countries,
            "action": r.action,
        }
        for r in rules
    ]


@router.get("/blocked-ips")
async def get_blocked_ips(
    db: AsyncSession = Depends(get_db),
):
    """Return all currently blocked IPs for Lua to cache."""
    from app.models.waf import ThreatActor
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(ThreatActor).where(
            ThreatActor.current_status.in_(["temp_blocked", "perm_blocked", "firewall_banned"])
        )
    )
    actors = result.scalars().all()

    blocked = []
    for actor in actors:
        # Skip expired temp blocks
        if actor.current_status == "temp_blocked" and actor.temp_block_until:
            if actor.temp_block_until < now:
                continue
        blocked.append({
            "ip": actor.ip_address,
            "status": actor.current_status,
            "until": actor.temp_block_until.isoformat() if actor.temp_block_until else None,
        })

    return blocked


@router.get("/rate-limits")
async def get_rate_limit_rules(
    db: AsyncSession = Depends(get_db),
):
    """Return all enabled rate limit rules for Lua to cache."""
    from app.models.rate_limit import RateLimitRule

    result = await db.execute(
        select(RateLimitRule).where(RateLimitRule.enabled == True)
    )
    rules = result.scalars().all()

    return [
        {
            "id": r.id,
            "proxy_host_id": r.proxy_host_id,
            "name": r.name,
            "requests_per_second": r.requests_per_second,
            "requests_per_minute": r.requests_per_minute,
            "requests_per_hour": r.requests_per_hour,
            "burst_size": r.burst_size,
            "action": r.action,
        }
        for r in rules
    ]


# ============================================================================
# Auth Wall Internal Endpoints (called by Lua)
# ============================================================================

class SessionValidateRequestBody(BaseModel):
    """Request body for session validation."""
    session_id: str
    auth_wall_id: str
    signature: str


@router.post("/auth-wall/validate-session", response_model=SessionValidateResponse)
async def validate_session(
    data: SessionValidateRequestBody,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate a session for Lua auth_wall.lua.
    Called on every request to protected hosts.
    """
    session_service = SessionService(db)

    # Verify cookie signature
    cookie_value = f"{data.session_id}.{data.signature}"
    verified_session_id = session_service.verify_session_cookie(cookie_value)

    if not verified_session_id:
        return SessionValidateResponse(valid=False)

    # Validate session in database
    session = await session_service.validate_session(
        session_id=verified_session_id,
        auth_wall_id=data.auth_wall_id,
    )

    if not session:
        return SessionValidateResponse(valid=False)

    # Return session info for Lua to set headers
    return SessionValidateResponse(
        valid=True,
        session_id=session.id,
        auth_wall_id=session.auth_wall_id,
        user_type=session.user_type,
        user_id=session.user_id,
        username=session.username,
        email=session.email,
        display_name=session.display_name,
        expires_at=int(session.expires_at.timestamp()),
    )


@router.get("/auth-wall/{auth_wall_id}/config", response_model=AuthWallConfigResponse)
async def get_auth_wall_config(
    auth_wall_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get auth wall configuration for Lua.
    Cached by Lua for 60 seconds.
    """
    result = await db.execute(
        select(AuthWall)
        .options(
            selectinload(AuthWall.auth_providers),
            selectinload(AuthWall.local_users),
            selectinload(AuthWall.ldap_configs),
        )
        .where(AuthWall.id == auth_wall_id)
    )
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    # Build provider list
    providers = [
        AuthWallConfigProvider(
            id=p.id,
            name=p.name,
            provider_type=p.provider_type,
            enabled=p.enabled,
        )
        for p in auth_wall.auth_providers
        if p.enabled
    ]

    return AuthWallConfigResponse(
        id=auth_wall.id,
        name=auth_wall.name,
        auth_type=auth_wall.auth_type,
        session_timeout=auth_wall.session_timeout,
        providers=providers,
        has_local_users=any(u.is_active for u in auth_wall.local_users),
        has_ldap=any(l.enabled for l in auth_wall.ldap_configs),
    )


class SessionActivityRequest(BaseModel):
    """Request to update session activity."""
    session_id: str


@router.post("/auth-wall/update-activity")
async def update_session_activity(
    data: SessionActivityRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update session last_activity_at.
    Called by Lua periodically (debounced).
    """
    session_service = SessionService(db)
    success = await session_service.update_activity(data.session_id)
    return {"updated": success}


# ============================================================================
# Push Notification Endpoint (called by updater sidecar)
# ============================================================================

class PushNotificationRequest(BaseModel):
    """Request to send push notification from updater."""
    title: str
    body: str
    notification_type: str = "general"
    data: Optional[dict] = None


@router.post("/push/send")
async def send_push_notification(
    data: PushNotificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Send push notification to all users.
    Called by updater sidecar for update status notifications.
    """
    # Verify internal auth token
    auth_token = request.headers.get("X-Internal-Auth")
    if auth_token != INTERNAL_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal auth token"
        )

    try:
        from app.services.push_service import push_service

        result = await push_service.notify_all(
            title=data.title,
            body=data.body,
            notification_type=data.notification_type,
            data=data.data,
            db=db,
        )
        return {"status": "sent", **result}
    except Exception as e:
        return {"status": "error", "error": str(e)}
