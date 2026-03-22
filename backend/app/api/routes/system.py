"""System monitoring API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.models.user import User
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
