"""add group_name to known_ips

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-09

A category says what an address is (office, vendor, scanner). A group ties many
addresses together as one thing — Microsoft publish Dataverse across 26 ranges
in Australia alone, and without a group those are 26 unrelated-looking rows.

Named group_name because "group" is reserved in SQL.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("known_ips", sa.Column("group_name", sa.String(length=100), nullable=True))
    op.create_index("ix_known_ips_group_name", "known_ips", ["group_name"])


def downgrade() -> None:
    op.drop_index("ix_known_ips_group_name", table_name="known_ips")
    op.drop_column("known_ips", "group_name")
