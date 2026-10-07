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
    if not _has_table("known_ips"):
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
    for name, columns in _INDEXES:
        if not _has_index("known_ips", name):
            op.create_index(name, "known_ips", columns)


def downgrade() -> None:
    for name, _columns in reversed(_INDEXES):
        if _has_index("known_ips", name):
            op.drop_index(name, table_name="known_ips")
    if _has_table("known_ips"):
        op.drop_table("known_ips")


_INDEXES = (
    ("ix_known_ips_ip_address", ["ip_address"]),
    ("ix_known_ips_category", ["category"]),
    ("idx_known_ips_category_label", ["category", "label"]),
)
