"""traffic rollups and traffic_logs index clean-up

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-08

The Traffic page aggregated straight over traffic_logs: /api/traffic/stats ran four
sequential scans of the last 30 days on every cache miss (every minute, since the
cache lived 30s and the page polled every 60s). This adds hourly summaries that the
page reads instead:

- traffic_rollup_hourly: per hour × proxy host × upstream (backend) × status code,
  with request/bot/failover/byte counts, response-time sum/count and a latency
  histogram.
- traffic_rollup_method_hourly: per hour × proxy host × method.
- traffic_rollup_state: how far the summaries are complete.

The tables start empty. The API's background job fills them, oldest hour first,
one day per step; until it catches up, queries read the rest from traffic_logs, so
nothing is ever missing or counted twice.

traffic_logs also loses two indexes that are prefixes of composite ones
(ix_traffic_logs_proxy_host_id is the head of idx_traffic_logs_host_timestamp,
ix_traffic_logs_timestamp of idx_traffic_logs_timestamp_status), which saves two
index writes per logged request, and gains an expression index on the backend's
host for the per-VM drill-down.

Idempotent: migration 0001 builds a fresh database from the live models with
create_all(), so on a new install all of this already exists.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# Same expression as app.models.traffic_log.UPSTREAM_HOST_SQL (copied, so this
# migration keeps working whatever later happens to the model).
UPSTREAM_HOST_SQL = r"regexp_replace(regexp_replace(coalesce(upstream_addr, ''), '^.*,\s*', ''), ':[0-9]+$', '')"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "traffic_rollup_hourly" not in tables:
        op.create_table(
            "traffic_rollup_hourly",
            sa.Column("bucket", sa.DateTime(timezone=True), primary_key=True),
            sa.Column("proxy_host_id", sa.String(36), primary_key=True),
            sa.Column("upstream", sa.String(255), primary_key=True),
            sa.Column("status", sa.SmallInteger(), primary_key=True),
            sa.Column("requests", sa.BigInteger(), nullable=False),
            sa.Column("bot_requests", sa.BigInteger(), nullable=False),
            sa.Column("failovers", sa.BigInteger(), nullable=False),
            sa.Column("bytes_sent", sa.BigInteger(), nullable=False),
            sa.Column("bytes_received", sa.BigInteger(), nullable=False),
            sa.Column("rt_count", sa.BigInteger(), nullable=False),
            sa.Column("rt_sum", sa.BigInteger(), nullable=False),
            sa.Column("rt_hist", postgresql.ARRAY(sa.BigInteger()), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_traffic_rollup_hourly_host_bucket", "traffic_rollup_hourly", ["proxy_host_id", "bucket"])
        op.create_index("idx_traffic_rollup_hourly_upstream_bucket", "traffic_rollup_hourly", ["upstream", "bucket"])

    if "traffic_rollup_method_hourly" not in tables:
        op.create_table(
            "traffic_rollup_method_hourly",
            sa.Column("bucket", sa.DateTime(timezone=True), primary_key=True),
            sa.Column("proxy_host_id", sa.String(36), primary_key=True),
            sa.Column("request_method", sa.String(10), primary_key=True),
            sa.Column("requests", sa.BigInteger(), nullable=False),
        )

    if "traffic_rollup_state" not in tables:
        op.create_table(
            "traffic_rollup_state",
            sa.Column("id", sa.SmallInteger(), primary_key=True),
            sa.Column("rolled_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Redundant single-column indexes (each is the leading column of a composite).
    op.execute("DROP INDEX IF EXISTS ix_traffic_logs_proxy_host_id")
    op.execute("DROP INDEX IF EXISTS ix_traffic_logs_timestamp")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_traffic_logs_upstream_host_ts "
        f"ON traffic_logs ({UPSTREAM_HOST_SQL}, timestamp)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_traffic_logs_upstream_host_ts")
    op.execute("CREATE INDEX IF NOT EXISTS ix_traffic_logs_timestamp ON traffic_logs (timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_traffic_logs_proxy_host_id ON traffic_logs (proxy_host_id)")
    tables = _tables()
    # Summaries only: every figure in them can be rebuilt from traffic_logs.
    for table in ("traffic_rollup_state", "traffic_rollup_method_hourly", "traffic_rollup_hourly"):
        if table in tables:
            op.drop_table(table)
