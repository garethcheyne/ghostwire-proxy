"""add abuseipdb blacklist cache table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

Adds `abuseipdb_blacklist`, a local cache of AbuseIPDB's /blacklist endpoint so
per-IP enrichment can check known-bad IPs for free instead of spending a
metered /check call on every honeypot hit. See app/models/honeypot.py
AbuseIPDBBlacklistEntry.
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import all models so Base.metadata is fully populated
    import app.models  # noqa: F401
    from app.core.database import Base

    # create_all with checkfirst=True: only creates tables that don't already
    # exist (i.e. just abuseipdb_blacklist), same pattern as 0001 baseline.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("abuseipdb_blacklist")
