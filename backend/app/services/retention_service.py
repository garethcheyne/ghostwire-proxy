"""
Data retention service — prunes old traffic_logs, threat_events, and audit_logs
based on configurable retention periods stored in the settings table.
Runs in batches to avoid long-running transactions and table locks.
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.setting import Setting

logger = logging.getLogger(__name__)

# Defaults match the settings table DEFAULT_SETTINGS in routes/settings.py
DEFAULT_RETENTION = {
    "traffic_log_retention_days": 30,
    "threat_event_retention_days": 90,
    "audit_log_retention_days": 90,
}

BATCH_SIZE = 5000  # Delete in batches to keep transactions short


async def _get_retention_setting(session: AsyncSession, key: str) -> int:
    """Get a retention setting value, falling back to hardcoded default."""
    result = await session.execute(select(Setting.value).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row is not None:
        try:
            return int(row)
        except (ValueError, TypeError):
            pass
    return DEFAULT_RETENTION.get(key, 90)


async def _batch_delete(session: AsyncSession, table_name: str, timestamp_col: str, cutoff: datetime) -> int:
    """Delete rows older than cutoff in batches. Returns total rows deleted."""
    total_deleted = 0
    while True:
        # Use a subquery to limit the delete to BATCH_SIZE rows
        result = await session.execute(
            text(
                f"DELETE FROM {table_name} WHERE id IN ("
                f"  SELECT id FROM {table_name} WHERE {timestamp_col} < :cutoff LIMIT :batch_size"
                f")"
            ),
            {"cutoff": cutoff, "batch_size": BATCH_SIZE},
        )
        deleted = result.rowcount
        await session.commit()
        total_deleted += deleted
        if deleted < BATCH_SIZE:
            break
    return total_deleted


async def run_retention_cleanup() -> dict:
    """
    Main entry point — reads retention settings and prunes old data.
    Returns a summary of what was deleted.
    """
    summary = {}

    async with AsyncSessionLocal() as session:
        # --- Traffic Logs ---
        days = await _get_retention_setting(session, "traffic_log_retention_days")
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            deleted = await _batch_delete(session, "traffic_logs", "timestamp", cutoff)
            summary["traffic_logs"] = {"deleted": deleted, "retention_days": days}
            if deleted > 0:
                logger.info(f"Retention: deleted {deleted} traffic_logs older than {days} days")

        # --- Threat Events ---
        days = await _get_retention_setting(session, "threat_event_retention_days")
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            deleted = await _batch_delete(session, "threat_events", "timestamp", cutoff)
            summary["threat_events"] = {"deleted": deleted, "retention_days": days}
            if deleted > 0:
                logger.info(f"Retention: deleted {deleted} threat_events older than {days} days")

        # --- Audit Logs ---
        days = await _get_retention_setting(session, "audit_log_retention_days")
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            deleted = await _batch_delete(session, "audit_logs", "timestamp", cutoff)
            summary["audit_logs"] = {"deleted": deleted, "retention_days": days}
            if deleted > 0:
                logger.info(f"Retention: deleted {deleted} audit_logs older than {days} days")

        # --- System Metrics (already had cleanup but wire it in here too) ---
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        deleted = await _batch_delete(session, "system_metrics", "timestamp", cutoff)
        summary["system_metrics"] = {"deleted": deleted, "retention_days": 90}
        if deleted > 0:
            logger.info(f"Retention: deleted {deleted} system_metrics older than 90 days")

        # --- VACUUM ANALYZE to reclaim space (PostgreSQL-specific) ---
        if any(v.get("deleted", 0) > 0 for v in summary.values()):
            try:
                # VACUUM requires being outside a transaction — use raw connection
                from app.core.database import engine
                from sqlalchemy import text as sa_text
                async with engine.connect() as conn:
                    await conn.execution_options(isolation_level="AUTOCOMMIT")
                    await conn.execute(sa_text("VACUUM ANALYZE traffic_logs"))
                    await conn.execute(sa_text("VACUUM ANALYZE threat_events"))
                    await conn.execute(sa_text("VACUUM ANALYZE audit_logs"))
                    await conn.execute(sa_text("VACUUM ANALYZE system_metrics"))
                logger.info("Retention: VACUUM ANALYZE completed")
            except Exception as e:
                logger.warning(f"Retention: VACUUM ANALYZE failed (non-fatal): {e}")

    return summary


async def get_table_sizes() -> dict:
    """Get approximate row counts and disk sizes for key tables."""
    async with AsyncSessionLocal() as session:
        sizes = {}
        tables = ["traffic_logs", "threat_events", "audit_logs", "system_metrics", "container_metrics"]
        for table in tables:
            try:
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                )
                count = result.scalar() or 0

                # PostgreSQL table size
                result = await session.execute(
                    text(f"SELECT pg_total_relation_size('{table}')")
                )
                size_bytes = result.scalar() or 0

                sizes[table] = {
                    "row_count": count,
                    "size_bytes": size_bytes,
                    "size_mb": round(size_bytes / (1024 * 1024), 1),
                }
            except Exception as e:
                sizes[table] = {"error": str(e)}

        # Total DB size
        try:
            result = await session.execute(
                text("SELECT pg_database_size(current_database())")
            )
            total = result.scalar() or 0
            sizes["_total"] = {
                "size_bytes": total,
                "size_mb": round(total / (1024 * 1024), 1),
            }
        except Exception as e:
            sizes["_total"] = {"error": str(e)}

    return sizes
