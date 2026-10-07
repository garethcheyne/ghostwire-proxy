"""Hourly summaries of traffic_logs, kept up to date by traffic_rollup_service.

The Traffic page and /api/traffic/stats aggregate over these instead of scanning
millions of raw rows: a 30-day window is ~720 buckets × hosts × backends × status
codes, not every request. Raw rows still answer anything finer (path, client IP,
user agent, …) and the not-yet-rolled-up tail; traffic_query stitches the two.

All hours before ``TrafficRollupState.rolled_until`` are complete; the tail after it
is always read from traffic_logs.
"""
from sqlalchemy import BigInteger, Column, DateTime, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.database import Base


class TrafficRollupHourly(Base):
    __tablename__ = "traffic_rollup_hourly"

    bucket = Column(DateTime(timezone=True), primary_key=True)  # UTC hour start
    proxy_host_id = Column(String(36), primary_key=True)
    # The upstream that produced the response ("10.0.0.5:8080"); the last address
    # when nginx tried several. '' when none was recorded (served by nginx itself).
    upstream = Column(String(255), primary_key=True, default="")
    status = Column(SmallInteger, primary_key=True)

    requests = Column(BigInteger, nullable=False, default=0)
    bot_requests = Column(BigInteger, nullable=False, default=0)
    # Requests nginx retried on another upstream before this one answered
    # (upstream_addr lists several addresses).
    failovers = Column(BigInteger, nullable=False, default=0)
    bytes_sent = Column(BigInteger, nullable=False, default=0)
    bytes_received = Column(BigInteger, nullable=False, default=0)
    # Response-time sum/count (rows with a time) and a fixed-bucket histogram for
    # percentiles; bounds in traffic_query.LATENCY_BOUNDS_MS.
    rt_count = Column(BigInteger, nullable=False, default=0)
    rt_sum = Column(BigInteger, nullable=False, default=0)
    rt_hist = Column(ARRAY(BigInteger), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_traffic_rollup_hourly_host_bucket", "proxy_host_id", "bucket"),
        Index("idx_traffic_rollup_hourly_upstream_bucket", "upstream", "bucket"),
    )


class TrafficRollupMethodHourly(Base):
    """Requests per method; kept apart so it doesn't multiply the main rollup."""

    __tablename__ = "traffic_rollup_method_hourly"

    bucket = Column(DateTime(timezone=True), primary_key=True)
    proxy_host_id = Column(String(36), primary_key=True)
    request_method = Column(String(10), primary_key=True)
    requests = Column(BigInteger, nullable=False, default=0)


class TrafficRollupState(Base):
    __tablename__ = "traffic_rollup_state"

    id = Column(SmallInteger, primary_key=True, default=1)
    # Every hour before this is summarised; NULL until the first run.
    rolled_until = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
