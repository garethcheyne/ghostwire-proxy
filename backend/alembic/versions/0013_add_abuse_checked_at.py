"""record when an IP's AbuseIPDB reputation was successfully fetched

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-10

Without this there was no way to tell "we asked AbuseIPDB and it said 0" from
"we have never asked", so every cache refresh looked like a miss and re-spent a
metered /check call. 641 calls in a single day were rejected with HTTP 429 as a
result.

Set once, on a successful lookup, and never cleared: an IP whose reputation we
already hold is never queried again.

Idempotent for the same reason as 0011/0012 — migration 0001 builds the baseline
from the live models with create_all().
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("ip_enrichments")}


def upgrade() -> None:
    if "abuse_checked_at" not in _columns():
        op.add_column(
            "ip_enrichments",
            sa.Column("abuse_checked_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Backfill: any row that already carries a score was, by definition, checked
    # successfully at some point. Stamp it so those IPs are never re-queried.
    op.execute(
        "UPDATE ip_enrichments "
        "SET abuse_checked_at = COALESCE(updated_at, enriched_at) "
        "WHERE abuse_score IS NOT NULL AND abuse_checked_at IS NULL"
    )


def downgrade() -> None:
    if "abuse_checked_at" in _columns():
        op.drop_column("ip_enrichments", "abuse_checked_at")
