"""proxy host groups and ordering

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-16

The Hosts page was one flat list, newest first. Groups give it named headings
("Media", "Dev", "Customer sites") and sort_order lets hosts and groups be put
in whatever order reads best. Layout only: nothing here reaches nginx.

Existing hosts start ungrouped, numbered in the order the page already showed
them (newest first), so nothing moves on upgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


# Idempotent: 0001 builds a fresh database from the live models with
# create_all(), so there this schema already exists when this runs.
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
    if not _has_table("proxy_host_groups"):
        op.create_table(
            "proxy_host_groups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False, unique=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _has_column("proxy_hosts", "group_id"):
        op.add_column(
            "proxy_hosts",
            sa.Column(
                "group_id",
                sa.String(length=36),
                sa.ForeignKey("proxy_host_groups.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _has_index("proxy_hosts", "ix_proxy_hosts_group_id"):
        op.create_index("ix_proxy_hosts_group_id", "proxy_hosts", ["group_id"])

    if not _has_column("proxy_hosts", "sort_order"):
        op.add_column(
            "proxy_hosts",
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        # Keep today's order (newest first) as the starting order.
        op.execute(
            """
            UPDATE proxy_hosts AS h
            SET sort_order = o.rn
            FROM (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at DESC, id) - 1 AS rn
                FROM proxy_hosts
            ) AS o
            WHERE h.id = o.id
            """
        )


def downgrade() -> None:
    if _has_column("proxy_hosts", "sort_order"):
        op.drop_column("proxy_hosts", "sort_order")
    if _has_index("proxy_hosts", "ix_proxy_hosts_group_id"):
        op.drop_index("ix_proxy_hosts_group_id", table_name="proxy_hosts")
    if _has_column("proxy_hosts", "group_id"):
        op.drop_column("proxy_hosts", "group_id")
    if _has_table("proxy_host_groups"):
        op.drop_table("proxy_host_groups")
