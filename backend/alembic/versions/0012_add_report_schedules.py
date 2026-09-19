"""add report_schedules for recurring emailed host reports

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-09

proxy_host_id is nullable = "all hosts", the same convention waf_rules,
rate_limit_rules and geoip_rules already use for global scope.

Idempotent for the same reason as 0011: migration 0001 creates the baseline from
the live models with `create_all()`, so on a fresh database this table already
exists before this migration runs.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _has_table("report_schedules"):
        op.create_table(
            "report_schedules",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("proxy_host_id", sa.String(length=36), nullable=True),
            sa.Column("frequency", sa.String(length=20), nullable=False, server_default="weekly"),
            sa.Column("send_hour", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("send_day", sa.Integer(), nullable=True),
            sa.Column("period", sa.String(length=10), nullable=False, server_default="7d"),
            sa.Column("recipients", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_status", sa.String(length=20), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _has_index("report_schedules", "ix_report_schedules_proxy_host_id"):
        op.create_index("ix_report_schedules_proxy_host_id", "report_schedules", ["proxy_host_id"])


def downgrade() -> None:
    if _has_index("report_schedules", "ix_report_schedules_proxy_host_id"):
        op.drop_index("ix_report_schedules_proxy_host_id", table_name="report_schedules")
    if _has_table("report_schedules"):
        op.drop_table("report_schedules")
