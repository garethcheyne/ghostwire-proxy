"""System monitoring API endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import socket

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.setting import Setting
from app.api.deps import get_current_user
from app.services.system_service import system_monitor_service

router = APIRouter()


class ServiceHealth(BaseModel):
    status: str  # healthy, unhealthy, unknown
    uptime: Optional[int] = None
    error: Optional[str] = None
    container_status: Optional[str] = None
    process: Optional[bool] = None


class CpuMetrics(BaseModel):
    usage: float
    cores: int


class MemoryMetrics(BaseModel):
    used: int
    total: int
    percent: float
    available: int


class DiskMetrics(BaseModel):
    used: int
    total: int
    percent: float
    free: int


class NetworkMetrics(BaseModel):
    bytes_sent_total: Optional[int] = None
    bytes_recv_total: Optional[int] = None
    bytes_sent_rate: Optional[int] = None
    bytes_recv_rate: Optional[int] = None


class ResourceMetrics(BaseModel):
    cpu: CpuMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    network: Optional[NetworkMetrics] = None


class ContainerInfo(BaseModel):
    name: str
    id: Optional[str] = None
    status: str
    cpu_percent: Optional[float] = None
    memory_used: Optional[int] = None
    memory_limit: Optional[int] = None
    memory_percent: Optional[float] = None
    network_rx_bytes: Optional[int] = None
    network_tx_bytes: Optional[int] = None
    started_at: Optional[str] = None
    uptime: Optional[str] = None
    error: Optional[str] = None


class DatabaseStats(BaseModel):
    size_bytes: Optional[int] = None
    connections: Optional[int] = None
    table_counts: Optional[dict] = None
    error: Optional[str] = None


class SystemStatusResponse(BaseModel):
    timestamp: str
    services: dict[str, ServiceHealth]
    resources: ResourceMetrics
    containers: list[ContainerInfo]
    database: DatabaseStats


class MetricsPoint(BaseModel):
    timestamp: str
    cpu_usage: Optional[float] = None
    memory_percent: Optional[float] = None
    memory_used: Optional[int] = None
    disk_percent: Optional[float] = None
    disk_used: Optional[int] = None
    network_bytes_sent: Optional[int] = None
    network_bytes_recv: Optional[int] = None
    request_count: Optional[int] = None
    active_connections: Optional[int] = None


class ThroughputPoint(BaseModel):
    timestamp: str
    requests: int
    bytes_sent: int
    bytes_received: int


@router.get("/status")
async def get_system_status(
    current_user: User = Depends(get_current_user),
) -> SystemStatusResponse:
    """
    Get current system status including all services, resources, and containers.

    Returns real-time metrics for:
    - Service health (API, Nginx, Redis, PostgreSQL)
    - Resource usage (CPU, Memory, Disk, Network)
    - Container status and resource usage
    - Database statistics
    """
    status = await system_monitor_service.get_system_status()
    return SystemStatusResponse(**status)


@router.get("/metrics")
async def get_metrics_history(
    period: str = Query("24h", pattern="^(1h|6h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MetricsPoint]:
    """
    Get historical system metrics.

    Period options:
    - 1h: Last hour (5-minute intervals)
    - 6h: Last 6 hours (15-minute intervals)
    - 24h: Last 24 hours (1-hour intervals)
    - 7d: Last 7 days (6-hour intervals)
    - 30d: Last 30 days (daily intervals)
    """
    metrics = await system_monitor_service.get_metrics_history(period, db)
    return [MetricsPoint(**m) for m in metrics]


@router.get("/throughput")
async def get_traffic_throughput(
    period: str = Query("24h", pattern="^(1h|6h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ThroughputPoint]:
    """
    Get traffic throughput metrics aggregated from traffic logs.

    Returns request counts and bytes transferred over time.
    """
    throughput = await system_monitor_service.get_traffic_throughput(period, db)
    return [ThroughputPoint(**t) for t in throughput]


@router.get("/containers")
async def get_containers(
    current_user: User = Depends(get_current_user),
) -> list[ContainerInfo]:
    """
    Get Docker container information for all ghostwire-proxy containers.
    """
    status = await system_monitor_service.get_system_status()
    return [ContainerInfo(**c) for c in status.get("containers", [])]


@router.post("/collect")
async def trigger_metrics_collection(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Manually trigger metrics collection.

    This is normally done automatically by the background task,
    but can be triggered manually if needed.
    """
    await system_monitor_service.collect_and_store_metrics()
    return {"status": "ok", "message": "Metrics collected successfully"}


@router.post("/cleanup")
async def cleanup_old_metrics(
    retention_days: int = Query(90, ge=1, le=365),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Clean up metrics older than the specified retention period.

    Default retention is 90 days.
    """
    await system_monitor_service.cleanup_old_metrics(retention_days)
    return {"status": "ok", "message": f"Cleaned up metrics older than {retention_days} days"}


# Kill Switch functionality
class KillSwitchRequest(BaseModel):
    active: bool
    mode: str = "maintenance"  # "maintenance", "redirect", "drop"
    redirect_url: Optional[str] = None


class KillSwitchResponse(BaseModel):
    active: bool
    mode: Optional[str] = None
    redirect_url: Optional[str] = None
    activated_at: Optional[str] = None
    activated_by: Optional[str] = None


def _generate_kill_switch_config(mode: str, redirect_url: Optional[str] = None) -> str:
    """Generate nginx config for the kill switch based on mode."""
    header = """# KILL SWITCH ACTIVE - All traffic blocked
# This file is auto-generated by Ghostwire Proxy kill switch
# Remove or replace this file to restore normal operation

server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name _;

    # Self-signed fallback cert for HTTPS
    ssl_certificate /etc/nginx/certs/default.crt;
    ssl_certificate_key /etc/nginx/certs/default.key;
"""

    if mode == "redirect":
        url = redirect_url or "https://example.com"
        body = f"""
    # Redirect all traffic
    location / {{
        return 301 {url};
    }}
}}
"""
    elif mode == "drop":
        body = """
    # Drop all connections immediately
    location / {
        return 444;
    }
}
"""
    else:  # maintenance (default)
        body = """
    # Block all traffic with 503 Service Unavailable
    location / {
        default_type text/html;
        return 503 '<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Service Unavailable</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
               background: #0f172a; color: #e2e8f0; display: flex; align-items: center;
               justify-content: center; min-height: 100vh; }
        .card { text-align: center; max-width: 480px; padding: 3rem; }
        .icon { font-size: 4rem; margin-bottom: 1.5rem; color: #ef4444; }
        h1 { font-size: 1.75rem; font-weight: 700; color: #ef4444; margin-bottom: 0.5rem; }
        p { color: #94a3b8; line-height: 1.6; }
        .badge { display: inline-block; margin-top: 1.5rem; padding: 0.5rem 1rem;
                 background: rgba(239,68,68,0.1); color: #ef4444; border-radius: 9999px;
                 font-size: 0.875rem; border: 1px solid rgba(239,68,68,0.3);
                 animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">&#9888;</div>
        <h1>Service Temporarily Unavailable</h1>
        <p>This service has been temporarily disabled by the administrator. Please contact your system administrator for more information.</p>
        <div class="badge">Emergency Maintenance Mode</div>
    </div>
</body>
</html>';
    }
}
"""

    return header + body


@router.get("/kill-switch")
async def get_kill_switch_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KillSwitchResponse:
    """
    Get the current kill switch status.
    """
    result = await db.execute(
        select(Setting).where(Setting.key == "kill_switch_active")
    )
    setting = result.scalar_one_or_none()

    active = setting.value == "true" if setting else False

    activated_at = None
    activated_by = None
    mode = None
    redirect_url = None

    if active:
        # Get activation details
        result = await db.execute(
            select(Setting).where(Setting.key == "kill_switch_activated_at")
        )
        at_setting = result.scalar_one_or_none()
        if at_setting:
            activated_at = at_setting.value

        result = await db.execute(
            select(Setting).where(Setting.key == "kill_switch_activated_by")
        )
        by_setting = result.scalar_one_or_none()
        if by_setting:
            activated_by = by_setting.value

        result = await db.execute(
            select(Setting).where(Setting.key == "kill_switch_mode")
        )
        mode_setting = result.scalar_one_or_none()
        mode = mode_setting.value if mode_setting else "maintenance"

        result = await db.execute(
            select(Setting).where(Setting.key == "kill_switch_redirect_url")
        )
        url_setting = result.scalar_one_or_none()
        if url_setting:
            redirect_url = url_setting.value

    return KillSwitchResponse(
        active=active,
        mode=mode,
        redirect_url=redirect_url,
        activated_at=activated_at,
        activated_by=activated_by,
    )


@router.post("/kill-switch")
async def toggle_kill_switch(
    request: KillSwitchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KillSwitchResponse:
    """
    Activate or deactivate the kill switch.

    Modes:
    - maintenance: Show 503 maintenance page
    - redirect: Redirect all traffic to a URL
    - drop: Drop connections (nginx 444 - close with no response)

    When deactivated, normal proxy configurations are restored.
    """
    if request.active and request.mode not in ("maintenance", "redirect", "drop"):
        raise HTTPException(status_code=400, detail="Invalid mode. Must be 'maintenance', 'redirect', or 'drop'")

    if request.active and request.mode == "redirect" and not request.redirect_url:
        raise HTTPException(status_code=400, detail="redirect_url is required for redirect mode")

    kill_switch_conf_path = os.path.join(settings.nginx_config_path, "_kill_switch.conf")
    backup_marker = os.path.join(settings.nginx_config_path, ".kill_switch_active")

    if request.active:
        # ACTIVATE kill switch
        # 1. Write kill switch config for the selected mode
        config = _generate_kill_switch_config(request.mode, request.redirect_url)
        with open(kill_switch_conf_path, "w") as f:
            f.write(config)

        # 2. Disable all other configs by renaming them
        for filename in os.listdir(settings.nginx_config_path):
            if filename.endswith(".conf") and filename != "_kill_switch.conf":
                filepath = os.path.join(settings.nginx_config_path, filename)
                os.rename(filepath, filepath + ".disabled")

        # 3. Mark kill switch as active
        with open(backup_marker, "w") as f:
            f.write(datetime.utcnow().isoformat())

        # 4. Save state to database
        await _save_setting(db, "kill_switch_active", "true")
        await _save_setting(db, "kill_switch_mode", request.mode)
        await _save_setting(db, "kill_switch_redirect_url", request.redirect_url or "")
        await _save_setting(db, "kill_switch_activated_at", datetime.utcnow().isoformat())
        await _save_setting(db, "kill_switch_activated_by", current_user.email)

        # 5. Reload nginx via Docker socket
        _reload_nginx_via_docker()

        await db.commit()

        return KillSwitchResponse(
            active=True,
            mode=request.mode,
            redirect_url=request.redirect_url,
            activated_at=datetime.utcnow().isoformat(),
            activated_by=current_user.email,
        )

    else:
        # DEACTIVATE kill switch
        # 1. Remove kill switch config
        if os.path.exists(kill_switch_conf_path):
            os.remove(kill_switch_conf_path)

        # 2. Restore all disabled configs
        for filename in os.listdir(settings.nginx_config_path):
            if filename.endswith(".conf.disabled"):
                filepath = os.path.join(settings.nginx_config_path, filename)
                os.rename(filepath, filepath[:-9])  # Remove .disabled suffix

        # 3. Remove kill switch marker
        if os.path.exists(backup_marker):
            os.remove(backup_marker)

        # 4. Update database
        await _save_setting(db, "kill_switch_active", "false")

        # 5. Reload nginx via Docker socket
        _reload_nginx_via_docker()

        await db.commit()

        return KillSwitchResponse(
            active=False,
            activated_at=None,
            activated_by=None,
        )


def _reload_nginx_via_docker():
    """Reload nginx in the nginx container via Docker socket SIGHUP."""
    docker_socket = "/var/run/docker.sock"
    if not os.path.exists(docker_socket):
        raise HTTPException(status_code=500, detail="Docker socket not available")
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(docker_socket)
        request = (
            "POST /containers/ghostwire-proxy-nginx/kill?signal=HUP HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Content-Length: 0\r\n\r\n"
        )
        sock.sendall(request.encode())
        sock.recv(4096)
        sock.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload nginx: {str(e)}")


async def _save_setting(db: AsyncSession, key: str, value: str) -> None:
    """Helper to save or update a setting."""
    result = await db.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)
