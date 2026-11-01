"""analytics byte counters to bigint

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-01

analytics_hourly / analytics_daily bytes_sent and bytes_received, and
analytics_geo.bytes, were int32. One host moving more than 2 GiB in a day made
every daily rollup fail with "value out of int32 range", so the whole rollup
transaction rolled back each hour and analytics_daily stopped advancing.

Widening int -> bigint keeps every existing value. Idempotent: only columns that
are still integer are altered (0001 builds fresh installs from the live models,
which are already BigInteger).
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

COLUMNS = {
    "analytics_hourly": ("bytes_sent", "bytes_received"),
    "analytics_daily": ("bytes_sent", "bytes_received"),
    "analytics_geo": ("bytes",),
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, names in COLUMNS.items():
        if not inspector.has_table(table):
            continue
        types = {c["name"]: c["type"] for c in inspector.get_columns(table)}
        for name in names:
            if name in types and not isinstance(types[name], sa.BigInteger):
                op.alter_column(table, name, type_=sa.BigInteger(), existing_type=sa.Integer())


def downgrade() -> None:
    # Narrowing could fail on (or truncate) values above 2^31; leave them wide.
    pass
