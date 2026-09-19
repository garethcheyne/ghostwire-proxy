"""add known_ips

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-09

Lets an operator put a name to an address. GeoIP tells you an IP is in
Amsterdam and belongs to some hosting company; only the operator knows it is
the office VPN, a customer, or their own monitoring. Without somewhere to record
that, every grid is a wall of anonymous numbers.

Exact addresses only for now. CIDR would need range matching on every lookup;
an exact address is one indexed hit, which is what makes annotating a grid of
50 log rows cheap.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "known_ips",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address"),
    )
    op.create_index("ix_known_ips_ip_address", "known_ips", ["ip_address"])
    op.create_index("ix_known_ips_category", "known_ips", ["category"])
    op.create_index("idx_known_ips_category_label", "known_ips", ["category", "label"])


def downgrade() -> None:
    op.drop_index("idx_known_ips_category_label", table_name="known_ips")
    op.drop_index("ix_known_ips_category", table_name="known_ips")
    op.drop_index("ix_known_ips_ip_address", table_name="known_ips")
    op.drop_table("known_ips")
