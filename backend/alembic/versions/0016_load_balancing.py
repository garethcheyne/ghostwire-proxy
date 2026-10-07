"""first-class load balancing for proxy hosts

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-07

Proxy hosts gain a balancing method (round robin, least connections, IP hash,
URI hash, random-of-two), an upstream keepalive size and per-host settings for
probing each upstream server. Upstream servers gain backup / down (maintenance)
/ max_conns and the per-server health state the background loop writes.

traffic_logs records which backend answered each request: the final
attempt's status, how many servers nginx tried, whether it failed over, the
per-attempt list (only when there was more than one) and the UpstreamServer it
resolved to, with an index for the per-backend breakdown of a host.

Existing hosts keep round robin with keepalive 32, which is exactly what the
generator emitted before, so their configs don't change.

Idempotent: migration 0001 builds a fresh database from the live models with
create_all(), so on a new install these columns already exist.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _host_columns() -> list[sa.Column]:
    return [
        sa.Column("lb_method", sa.String(20), nullable=False, server_default="round_robin"),
        sa.Column("upstream_keepalive", sa.Integer(), nullable=False, server_default="32"),
        sa.Column("health_check_type", sa.String(10), nullable=False, server_default="http"),
        sa.Column("health_check_path", sa.String(255), nullable=False, server_default="/"),
        sa.Column("health_check_timeout", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("lb_auto_down", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]


def _server_columns() -> list[sa.Column]:
    return [
        sa.Column("backup", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("down", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_conns", sa.Integer(), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("auto_down", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]


def _traffic_columns() -> list[sa.Column]:
    return [
        sa.Column("upstream_status", sa.Integer(), nullable=True),
        sa.Column("upstream_attempts", sa.SmallInteger(), nullable=True),
        sa.Column("upstream_failover", sa.Boolean(), nullable=True),
        sa.Column("upstream_attempt_log", sa.JSON(), nullable=True),
        sa.Column("upstream_server_id", sa.String(36), nullable=True),
    ]


TRAFFIC_INDEX = "idx_traffic_logs_host_upstream_server_ts"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, columns in (
        ("proxy_hosts", _host_columns()),
        ("upstream_servers", _server_columns()),
        ("traffic_logs", _traffic_columns()),
    ):
        existing = _columns(table)
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    # Plain CREATE INDEX like 0018: it reads traffic_logs once and holds off
    # log writes while it builds (seconds for a few million rows).
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {TRAFFIC_INDEX} "
        "ON traffic_logs (proxy_host_id, upstream_server_id, timestamp)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {TRAFFIC_INDEX}")
    for table, columns in (
        ("traffic_logs", _traffic_columns()),
        ("upstream_servers", _server_columns()),
        ("proxy_hosts", _host_columns()),
    ):
        existing = _columns(table)
        for column in reversed(columns):
            if column.name in existing:
                op.drop_column(table, column.name)
