"""add response-time percentiles, bot counts, and connection classification

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-09

Three related additions, all in service of making latency numbers honest:

- p95/p99 on the analytics rollups. A mean is useless here: fleet traffic has a
  30ms median and a 60s p95 (requests dying at proxy_read_timeout), which the
  mean reports as "13 seconds" and nobody can act on.
- is_streaming on traffic_logs. Websocket upgrades and SSE streams stay open for
  minutes by design; their duration is connection lifetime, not server latency,
  and including them is what makes the tail unreadable.
- is_bot on traffic_logs plus bot_requests on the rollups, so "unique visitors"
  can eventually mean humans.

All columns are nullable: NULL means "written before classification existed",
which is deliberately distinguishable from False.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_ROLLUP_TABLES = ("analytics_hourly", "analytics_daily")


# Idempotent: migration 0001 builds a fresh database from the live models with
# create_all(), so there this schema already exists when this runs, while an
# existing database does not have it yet. Guarding on the actual schema keeps
# the effect on existing databases unchanged and lets a fresh install finish.
def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    for table in _ROLLUP_TABLES:
        if not _has_column(table, "p95_response_time_ms"):
            op.add_column(table, sa.Column("p95_response_time_ms", sa.Integer(), nullable=True))
        if not _has_column(table, "p99_response_time_ms"):
            op.add_column(table, sa.Column("p99_response_time_ms", sa.Integer(), nullable=True))
        if not _has_column(table, "bot_requests"):
            op.add_column(table, sa.Column("bot_requests", sa.Integer(), nullable=True, server_default="0"))

    # Nullable with no default, so adding these to a large traffic_logs table is
    # a metadata-only change rather than a full rewrite.
    if not _has_column("traffic_logs", "is_bot"):
        op.add_column("traffic_logs", sa.Column("is_bot", sa.Boolean(), nullable=True))
    if not _has_column("traffic_logs", "is_streaming"):
        op.add_column("traffic_logs", sa.Column("is_streaming", sa.Boolean(), nullable=True))
    if not _has_index("traffic_logs", "ix_traffic_logs_is_bot"):
        op.create_index("ix_traffic_logs_is_bot", "traffic_logs", ["is_bot"])


def downgrade() -> None:
    if _has_index("traffic_logs", "ix_traffic_logs_is_bot"):
        op.drop_index("ix_traffic_logs_is_bot", table_name="traffic_logs")
    for column in ("is_streaming", "is_bot"):
        if _has_column("traffic_logs", column):
            op.drop_column("traffic_logs", column)
    for table in _ROLLUP_TABLES:
        for column in ("bot_requests", "p99_response_time_ms", "p95_response_time_ms"):
            if _has_column(table, column):
                op.drop_column(table, column)
