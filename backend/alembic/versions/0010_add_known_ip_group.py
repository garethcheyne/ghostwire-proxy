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
    if not _has_column("known_ips", "group_name"):
        op.add_column("known_ips", sa.Column("group_name", sa.String(length=100), nullable=True))
    if not _has_index("known_ips", "ix_known_ips_group_name"):
        op.create_index("ix_known_ips_group_name", "known_ips", ["group_name"])


def downgrade() -> None:
    if _has_index("known_ips", "ix_known_ips_group_name"):
        op.drop_index("ix_known_ips_group_name", table_name="known_ips")
    if _has_column("known_ips", "group_name"):
        op.drop_column("known_ips", "group_name")
