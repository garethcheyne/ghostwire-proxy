"""
System monitoring service for collecting metrics from the host system,
Docker containers, and database.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

import psutil

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.core.database import AsyncSessionLocal, engine
from app.models.system_metrics import SystemMetrics, ContainerMetrics
from app.models.traffic_log import TrafficLog

logger = logging.getLogger(__name__)

# Try to import Docker SDK (optional dependency)
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger.info("Docker SDK not available - container metrics will be limited")


class SystemMonitorService:
    """Service for collecting and storing system metrics."""

    def __init__(self):
        self._docker_client = None
        self._last_network_counters = None
        self._last_network_time = None

    @property
    def docker_client(self):
        """Lazy-load Docker client."""
        if not DOCKER_AVAILABLE:
            return None
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env()
            except Exception as e:
                logger.warning(f"Could not connect to Docker: {e}")
                return None
        return self._docker_client

    async def get_system_status(self) -> dict:
        """Get current system status including all services."""
        now = datetime.now(timezone.utc)

        # Get service health
        services = await self._get_services_health()

        # Get resource metrics
        resources = self._get_resource_metrics()

        # Get container info
        containers = await self._get_container_info()

        # Get database stats
        db_stats = await self._get_database_stats()

        return {
            "timestamp": now.isoformat(),
            "services": services,
            "resources": resources,
            "containers": containers,
            "database": db_stats,
        }

    async def _get_services_health(self) -> dict:
        """Check health of all services."""
        services = {}

        # API is healthy if we're running
        services["api"] = {
            "status": "healthy",
            "uptime": self._get_process_uptime(),
        }

        # Check PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            services["postgres"] = {"status": "healthy"}
        except Exception as e:
            services["postgres"] = {"status": "unhealthy", "error": str(e)}

        # Check Redis
        try:
            from app.core.redis import redis_pool
            if redis_pool:
                async with redis_pool.client() as client:
                    await client.ping()
                services["redis"] = {"status": "healthy"}
            else:
                services["redis"] = {"status": "unknown", "error": "Redis pool not initialized"}
        except Exception as e:
            services["redis"] = {"status": "unhealthy", "error": str(e)}

        # Check Nginx via Docker or process
        nginx_status = await self._check_nginx_health()
        services["nginx"] = nginx_status

        return services

    async def _check_nginx_health(self) -> dict:
        """Check Nginx health status."""
        if self.docker_client:
            try:
                containers = self.docker_client.containers.list(
                    filters={"name": "ghostwire-proxy-nginx"}
                )
                if containers:
                    container = containers[0]
                    if container.status == "running":
                        return {"status": "healthy", "container_status": container.status}
                    return {"status": "unhealthy", "container_status": container.status}
                return {"status": "unknown", "error": "Container not found"}
            except Exception as e:
                logger.debug(f"Docker check failed: {e}")

        # Fallback: check if nginx process is running
        for proc in psutil.process_iter(['name']):
            try:
                if 'nginx' in proc.info['name'].lower():
                    return {"status": "healthy", "process": True}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return {"status": "unknown"}

    def _get_process_uptime(self) -> int:
        """Get current process uptime in seconds."""
        try:
            process = psutil.Process(os.getpid())
            return int(datetime.now().timestamp() - process.create_time())
        except Exception:
            return 0

    def _get_resource_metrics(self) -> dict:
        """Get current system resource metrics."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()

        # Memory
        memory = psutil.virtual_memory()

        # Disk (use /data if available, else /)
        disk_path = "/data" if os.path.exists("/data") else "/"
        try:
            disk = psutil.disk_usage(disk_path)
        except Exception:
            disk = psutil.disk_usage("/")

        # Network
        network = self._get_network_rates()

        return {
            "cpu": {
                "usage": round(cpu_percent, 1),
                "cores": cpu_count,
            },
            "memory": {
                "used": memory.used,
                "total": memory.total,
                "percent": round(memory.percent, 1),
                "available": memory.available,
            },
            "disk": {
                "used": disk.used,
                "total": disk.total,
                "percent": round(disk.percent, 1),
                "free": disk.free,
            },
            "network": network,
        }

    def _get_network_rates(self) -> dict:
        """Calculate network I/O rates."""
        try:
            counters = psutil.net_io_counters()
            now = datetime.now()

            if self._last_network_counters and self._last_network_time:
                time_diff = (now - self._last_network_time).total_seconds()
                if time_diff > 0:
                    bytes_sent_rate = (counters.bytes_sent - self._last_network_counters.bytes_sent) / time_diff
                    bytes_recv_rate = (counters.bytes_recv - self._last_network_counters.bytes_recv) / time_diff
                else:
                    bytes_sent_rate = 0
                    bytes_recv_rate = 0
            else:
                bytes_sent_rate = 0
                bytes_recv_rate = 0

            self._last_network_counters = counters
            self._last_network_time = now

            return {
                "bytes_sent_total": counters.bytes_sent,
                "bytes_recv_total": counters.bytes_recv,
                "bytes_sent_rate": round(bytes_sent_rate),
                "bytes_recv_rate": round(bytes_recv_rate),
            }
        except Exception as e:
            logger.debug(f"Could not get network stats: {e}")
            return {}

    async def _get_container_info(self) -> list:
        """Get Docker container information."""
        containers = []

        if not self.docker_client:
            return containers

        try:
            # Filter for ghostwire-proxy containers
            docker_containers = self.docker_client.containers.list(
                all=True,
                filters={"name": "ghostwire-proxy"}
            )

            for container in docker_containers:
                try:
                    # Get container stats
                    stats = container.stats(stream=False)

                    # Calculate CPU percentage
                    cpu_percent = self._calculate_container_cpu(stats)

                    # Calculate memory usage
                    memory_stats = stats.get("memory_stats", {})
                    memory_used = memory_stats.get("usage", 0)
                    memory_limit = memory_stats.get("limit", 0)
                    memory_percent = (memory_used / memory_limit * 100) if memory_limit > 0 else 0

                    # Get network stats
                    networks = stats.get("networks", {})
                    network_rx = sum(n.get("rx_bytes", 0) for n in networks.values())
                    network_tx = sum(n.get("tx_bytes", 0) for n in networks.values())

                    # Parse started time
                    started_at = None
                    if container.attrs.get("State", {}).get("StartedAt"):
                        try:
                            started_str = container.attrs["State"]["StartedAt"]
                            if started_str and started_str != "0001-01-01T00:00:00Z":
                                # Handle nanoseconds in timestamp
                                if "." in started_str:
                                    started_str = started_str.split(".")[0] + "Z"
                                started_at = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    containers.append({
                        "name": container.name,
                        "id": container.short_id,
                        "status": container.status,
                        "cpu_percent": round(cpu_percent, 1),
                        "memory_used": memory_used,
                        "memory_limit": memory_limit,
                        "memory_percent": round(memory_percent, 1),
                        "network_rx_bytes": network_rx,
                        "network_tx_bytes": network_tx,
                        "started_at": started_at.isoformat() if started_at else None,
                        "uptime": self._calculate_uptime(started_at) if started_at else None,
                    })
                except Exception as e:
                    logger.debug(f"Error getting stats for container {container.name}: {e}")
                    containers.append({
                        "name": container.name,
                        "id": container.short_id,
                        "status": container.status,
                        "error": str(e),
                    })

        except Exception as e:
            logger.warning(f"Error listing containers: {e}")

        return containers

    def _calculate_container_cpu(self, stats: dict) -> float:
        """Calculate container CPU percentage from Docker stats."""
        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_usage = cpu_stats.get("cpu_usage", {})
            precpu_usage = precpu_stats.get("cpu_usage", {})

            cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)

            if system_delta > 0 and cpu_delta > 0:
                cpu_count = len(cpu_usage.get("percpu_usage", [])) or 1
                return (cpu_delta / system_delta) * cpu_count * 100

            return 0.0
        except Exception:
            return 0.0

    def _calculate_uptime(self, started_at: datetime) -> str:
        """Calculate human-readable uptime string."""
        if not started_at:
            return None

        now = datetime.now(timezone.utc)
        delta = now - started_at

        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    async def _get_database_stats(self) -> dict:
        """Get PostgreSQL database statistics."""
        try:
            async with AsyncSessionLocal() as session:
                # Get database size
                size_result = await session.execute(
                    text("SELECT pg_database_size(current_database())")
                )
                db_size = size_result.scalar() or 0

                # Get connection count
                conn_result = await session.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                )
                connections = conn_result.scalar() or 0

                # Get table counts
                table_counts = {}
                for table in ["traffic_logs", "proxy_hosts", "certificates", "users"]:
                    try:
                        count_result = await session.execute(
                            text(f"SELECT count(*) FROM {table}")
                        )
                        table_counts[table] = count_result.scalar() or 0
                    except Exception:
                        pass

                return {
                    "size_bytes": db_size,
                    "connections": connections,
                    "table_counts": table_counts,
                }
        except Exception as e:
            logger.warning(f"Could not get database stats: {e}")
            return {"error": str(e)}

    async def get_metrics_history(
        self,
        period: str = "24h",
        db: AsyncSession = None
    ) -> list:
        """Get historical system metrics."""
        period_map = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }

        delta = period_map.get(period, timedelta(hours=24))
        start_time = datetime.now(timezone.utc) - delta

        if db is None:
            async with AsyncSessionLocal() as session:
                return await self._fetch_metrics_history(session, start_time)
        return await self._fetch_metrics_history(db, start_time)

    async def _fetch_metrics_history(
        self,
        db: AsyncSession,
        start_time: datetime
    ) -> list:
        """Fetch metrics from database."""
        query = (
            select(SystemMetrics)
            .where(SystemMetrics.timestamp >= start_time)
            .order_by(SystemMetrics.timestamp)
        )
        result = await db.execute(query)
        metrics = result.scalars().all()

        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_usage": m.cpu_usage,
                "memory_percent": m.memory_percent,
                "memory_used": m.memory_used,
                "disk_percent": m.disk_percent,
                "disk_used": m.disk_used,
                "network_bytes_sent": m.network_bytes_sent,
                "network_bytes_recv": m.network_bytes_recv,
                "request_count": m.request_count,
                "active_connections": m.active_connections,
            }
            for m in metrics
        ]

    async def get_traffic_throughput(
        self,
        period: str = "24h",
        db: AsyncSession = None
    ) -> list:
        """Get traffic throughput metrics from traffic logs."""
        period_map = {
            "1h": (timedelta(hours=1), timedelta(minutes=5)),
            "6h": (timedelta(hours=6), timedelta(minutes=15)),
            "24h": (timedelta(hours=24), timedelta(hours=1)),
            "7d": (timedelta(days=7), timedelta(hours=6)),
            "30d": (timedelta(days=30), timedelta(days=1)),
        }

        total_delta, interval = period_map.get(period, (timedelta(hours=24), timedelta(hours=1)))
        start_time = datetime.now(timezone.utc) - total_delta

        if db is None:
            async with AsyncSessionLocal() as session:
                return await self._fetch_traffic_throughput(session, start_time, interval)
        return await self._fetch_traffic_throughput(db, start_time, interval)

    async def _fetch_traffic_throughput(
        self,
        db: AsyncSession,
        start_time: datetime,
        interval: timedelta
    ) -> list:
        """Aggregate traffic logs into throughput data."""
        now = datetime.now(timezone.utc)
        throughput = []
        current = start_time

        while current < now:
            bucket_end = current + interval

            query = select(
                func.count(TrafficLog.id),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
                func.coalesce(func.sum(TrafficLog.bytes_received), 0),
            ).where(
                TrafficLog.timestamp >= current,
                TrafficLog.timestamp < bucket_end
            )

            result = await db.execute(query)
            row = result.first()

            throughput.append({
                "timestamp": current.isoformat(),
                "requests": row[0] or 0,
                "bytes_sent": row[1] or 0,
                "bytes_received": row[2] or 0,
            })

            current = bucket_end

        return throughput

    async def collect_and_store_metrics(self):
        """Collect current metrics and store in database."""
        try:
            resources = self._get_resource_metrics()
            network = self._get_network_rates()

            # Get request count for the last minute
            async with AsyncSessionLocal() as session:
                one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
                req_count = await session.execute(
                    select(func.count(TrafficLog.id)).where(
                        TrafficLog.timestamp >= one_min_ago
                    )
                )
                request_count = req_count.scalar() or 0

                # Get database stats
                db_stats = await self._get_database_stats()

                # Create metrics record
                metrics = SystemMetrics(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc),
                    cpu_usage=resources["cpu"]["usage"],
                    cpu_count=resources["cpu"]["cores"],
                    memory_used=resources["memory"]["used"],
                    memory_total=resources["memory"]["total"],
                    memory_percent=resources["memory"]["percent"],
                    disk_used=resources["disk"]["used"],
                    disk_total=resources["disk"]["total"],
                    disk_percent=resources["disk"]["percent"],
                    network_bytes_sent=network.get("bytes_sent_total"),
                    network_bytes_recv=network.get("bytes_recv_total"),
                    request_count=request_count,
                    db_connections=db_stats.get("connections"),
                    db_size_bytes=db_stats.get("size_bytes"),
                )

                session.add(metrics)
                await session.commit()

                logger.debug("Stored system metrics")

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

    async def cleanup_old_metrics(self, retention_days: int = 90):
        """Delete metrics older than retention period."""
        try:
            async with AsyncSessionLocal() as session:
                cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

                # Delete old system metrics
                await session.execute(
                    text("DELETE FROM system_metrics WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff}
                )

                # Delete old container metrics
                await session.execute(
                    text("DELETE FROM container_metrics WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff}
                )

                await session.commit()
                logger.info(f"Cleaned up metrics older than {retention_days} days")

        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {e}")


# Global service instance
system_monitor_service = SystemMonitorService()
