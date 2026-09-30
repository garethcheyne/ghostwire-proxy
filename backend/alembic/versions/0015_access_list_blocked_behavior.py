"""what an IP access list does with a blocked visitor

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-30

Until now a blocked visitor always got nginx's 403. The same choices as the
Default Site are now available per list: the Ghostwire welcome page, a redirect,
404, or dropping the connection. Existing lists keep 403.

Idempotent for the same reason as 0011-0013 — migration 0001 builds the baseline
from the live models with create_all().
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("access_lists")}


def upgrade() -> None:
    columns = _columns()
    if "blocked_behavior" not in columns:
        op.add_column(
            "access_lists",
            sa.Column("blocked_behavior", sa.String(20), nullable=False, server_default="403"),
        )
    if "blocked_redirect_url" not in columns:
        op.add_column("access_lists", sa.Column("blocked_redirect_url", sa.String(2048), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if "blocked_redirect_url" in columns:
        op.drop_column("access_lists", "blocked_redirect_url")
    if "blocked_behavior" in columns:
        op.drop_column("access_lists", "blocked_behavior")
