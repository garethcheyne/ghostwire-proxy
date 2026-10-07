"""Keeps traffic_rollup_hourly / traffic_rollup_method_hourly in step with traffic_logs.

Each run recomputes whole hours from raw rows: delete the hours' summary rows,
then insert them again from a GROUP BY. That makes a run idempotent and lets it
re-read the last couple of hours, picking up log lines that arrived late.

``traffic_rollup_state.rolled_until`` marks the end of what is summarised; every
hour before it is complete. Readers (traffic_query) take hours before it from the
rollup and everything after from traffic_logs, so a stalled or not-yet-started
job only makes queries slower, never wrong.

A first run on an existing install backfills from the oldest log row, one day
per transaction, oldest first, so it can stop and resume at any point.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.traffic_log import UPSTREAM_SQL
from app.services.traffic_query import FAILOVER_SQL, HIST_LEN, WB_SQL, floor_hour

logger = logging.getLogger(__name__)

# Hours re-read on every run, for log lines that reach the API late.
RECOMPUTE = timedelta(hours=2)
# One transaction covers at most this much (backfill steps).
STEP = timedelta(days=1)
# pg advisory lock id: only one process rolls up at a time.
_LOCK_ID = 0x6777_726F  # "gwro"

_HIST_COLS = ", ".join(f"count(*) FILTER (WHERE wb = {i})" for i in range(HIST_LEN))

_INSERT_HOURLY = f"""
INSERT INTO traffic_rollup_hourly
    (bucket, proxy_host_id, upstream, status, requests, bot_requests, failovers, bytes_sent,
     bytes_received, rt_count, rt_sum, rt_hist, last_seen)
SELECT bucket, proxy_host_id, upstream, status,
       count(*),
       count(*) FILTER (WHERE is_bot IS TRUE),
       count(*) FILTER (WHERE failover),
       coalesce(sum(bytes_sent), 0),
       coalesce(sum(bytes_received), 0),
       count(wb),
       coalesce(sum(response_time) FILTER (WHERE wb IS NOT NULL), 0),
       ARRAY[{_HIST_COLS}]::bigint[],
       max(timestamp)
FROM (
    SELECT date_trunc('hour', timestamp, 'UTC') AS bucket, proxy_host_id,
           {UPSTREAM_SQL} AS upstream, status, is_bot, {FAILOVER_SQL} AS failover,
           bytes_sent, bytes_received,
           response_time, timestamp, {WB_SQL} AS wb
    FROM traffic_logs
    WHERE timestamp >= :start AND timestamp < :end
) r
GROUP BY 1, 2, 3, 4
"""

_INSERT_METHODS = """
INSERT INTO traffic_rollup_method_hourly (bucket, proxy_host_id, request_method, requests)
SELECT date_trunc('hour', timestamp, 'UTC'), proxy_host_id, request_method, count(*)
FROM traffic_logs
WHERE timestamp >= :start AND timestamp < :end
GROUP BY 1, 2, 3
"""


async def rebuild(db: AsyncSession, start: datetime, end: datetime) -> None:
    """Recompute the summary rows for hours in [start, end) (hour-aligned)."""
    params = {"start": start, "end": end}
    await db.execute(text("DELETE FROM traffic_rollup_hourly WHERE bucket >= :start AND bucket < :end"), params)
    await db.execute(text("DELETE FROM traffic_rollup_method_hourly WHERE bucket >= :start AND bucket < :end"), params)
    await db.execute(text(_INSERT_HOURLY), params)
    await db.execute(text(_INSERT_METHODS), params)


async def _state(db: AsyncSession) -> Optional[datetime]:
    return (await db.execute(text("SELECT rolled_until FROM traffic_rollup_state WHERE id = 1"))).scalar()


async def _set_state(db: AsyncSession, until: datetime) -> None:
    await db.execute(
        text(
            "INSERT INTO traffic_rollup_state (id, rolled_until, updated_at) VALUES (1, :u, now()) "
            "ON CONFLICT (id) DO UPDATE SET rolled_until = GREATEST(traffic_rollup_state.rolled_until, EXCLUDED.rolled_until), "
            "updated_at = now()"
        ),
        {"u": until},
    )


async def _try_lock(db: AsyncSession) -> bool:
    return bool((await db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _LOCK_ID})).scalar())


async def refresh(
    now: Optional[datetime] = None, *, max_steps: int = 1000,
    session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
) -> dict:
    """Bring the rollup up to the start of the current hour. Returns what it did."""
    now = now or datetime.now(timezone.utc)
    current = floor_hour(now)
    steps = 0
    first_start: Optional[datetime] = None
    end: Optional[datetime] = None
    while steps < max_steps:
        async with session_factory() as db:
            if not await _try_lock(db):
                return {"status": "busy"}
            state = await _state(db)
            if state is None:
                oldest = (await db.execute(text("SELECT min(timestamp) FROM traffic_logs"))).scalar()
                start = floor_hour(oldest) if oldest else current
            elif steps == 0:
                start = min(state, current) - RECOMPUTE
            else:
                start = state
            if start >= current and state is not None:
                await db.commit()
                break
            end = min(current, start + STEP)
            if end > start:
                await rebuild(db, start, end)
            await _set_state(db, end)
            await db.commit()
            first_start = first_start or start
            steps += 1
            if end >= current:
                break
    return {"status": "ok", "from": first_start, "until": end, "steps": steps}


async def rebuild_hour_of(db: AsyncSession, ts: datetime) -> None:
    """Recompute the hour holding ``ts`` if it's already summarised (after a row
    in it was deleted). Runs in the caller's transaction."""
    state = await _state(db)
    hour = floor_hour(ts.astimezone(timezone.utc))
    if state is not None and hour < state:
        await rebuild(db, hour, hour + timedelta(hours=1))


async def prune_before(db: AsyncSession, cutoff: datetime) -> None:
    """After retention deleted raw rows older than ``cutoff``: drop the hours
    wholly before it and recompute the one it cuts through, so the summaries
    describe exactly the rows that still exist."""
    hour = floor_hour(cutoff.astimezone(timezone.utc))
    params = {"h": hour}
    await db.execute(text("DELETE FROM traffic_rollup_hourly WHERE bucket < :h"), params)
    await db.execute(text("DELETE FROM traffic_rollup_method_hourly WHERE bucket < :h"), params)
    await rebuild_hour_of(db, cutoff)


async def clear(db: AsyncSession) -> None:
    """Every traffic log was purged: the summaries go too."""
    await db.execute(text("DELETE FROM traffic_rollup_hourly"))
    await db.execute(text("DELETE FROM traffic_rollup_method_hourly"))
