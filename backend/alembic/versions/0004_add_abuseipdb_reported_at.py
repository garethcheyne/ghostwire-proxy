"""add abuseipdb_reported_at to threat_actors

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

Tracks when a threat_actors row was last submitted to AbuseIPDB via
bulk-report, so submit_bulk_reports() only re-reports an IP once new
activity (last_seen) has occurred since the last report - not on every
sync run. See app/services/abuseipdb_report_service.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "threat_actors",
        sa.Column("abuseipdb_reported_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("threat_actors", "abuseipdb_reported_at")
