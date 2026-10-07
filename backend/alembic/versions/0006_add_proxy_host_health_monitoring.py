"""add upstream health monitoring columns to proxy_hosts

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08

Backs the background health-check loop that probes each enabled host's upstream
and raises a push notification when a host goes down or recovers. The state is
persisted (rather than kept in memory) so that a restart does not re-announce
outages that were already reported.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


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
    if not _has_column("proxy_hosts", "health_check_enabled"):
        op.add_column(
            "proxy_hosts",
            sa.Column("health_check_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        # Server default was only needed to backfill existing rows.
        op.alter_column("proxy_hosts", "health_check_enabled",
                        existing_type=sa.Boolean(), existing_nullable=False, server_default=None)
    if not _has_column("proxy_hosts", "health_status"):
        op.add_column(
            "proxy_hosts",
            sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
        )
        op.alter_column("proxy_hosts", "health_status",
                        existing_type=sa.String(length=20), existing_nullable=False, server_default=None)
    if not _has_column("proxy_hosts", "health_checked_at"):
        op.add_column(
            "proxy_hosts",
            sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column("proxy_hosts", "health_error"):
        op.add_column("proxy_hosts", sa.Column("health_error", sa.Text(), nullable=True))


def downgrade() -> None:
    for name in ("health_error", "health_checked_at", "health_status", "health_check_enabled"):
        if _has_column("proxy_hosts", name):
            op.drop_column("proxy_hosts", name)
