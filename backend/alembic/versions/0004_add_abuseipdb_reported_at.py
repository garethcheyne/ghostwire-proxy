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
    if not _has_column("threat_actors", "abuseipdb_reported_at"):
        op.add_column(
            "threat_actors",
            sa.Column("abuseipdb_reported_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _has_column("threat_actors", "abuseipdb_reported_at"):
        op.drop_column("threat_actors", "abuseipdb_reported_at")
