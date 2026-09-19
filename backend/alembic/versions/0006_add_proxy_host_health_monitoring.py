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


def upgrade() -> None:
    op.add_column(
        "proxy_hosts",
        sa.Column("health_check_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "proxy_hosts",
        sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "proxy_hosts",
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("proxy_hosts", sa.Column("health_error", sa.Text(), nullable=True))

    # Server defaults were only needed to backfill existing rows.
    op.alter_column("proxy_hosts", "health_check_enabled",
                    existing_type=sa.Boolean(), existing_nullable=False, server_default=None)
    op.alter_column("proxy_hosts", "health_status",
                    existing_type=sa.String(length=20), existing_nullable=False, server_default=None)


def downgrade() -> None:
    for name in ("health_error", "health_checked_at", "health_status", "health_check_enabled"):
        op.drop_column("proxy_hosts", name)
