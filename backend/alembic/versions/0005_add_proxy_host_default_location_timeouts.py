"""add default-location proxy timeouts to proxy_hosts

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08

The generated default ("/") location block previously hardcoded
`proxy_connect_timeout` / `proxy_send_timeout` / `proxy_read_timeout` to 60s
with no way to change them - ProxyLocation had these columns but ProxyHost did
not, so hosts served entirely by the default location were stuck at 60s. These
columns give the default location the same per-host control custom locations
already had. See app/services/openresty_service.py::_generate_default_location.

Defaults are 60 so existing hosts keep generating byte-identical config.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_COLUMNS = (
    "proxy_connect_timeout",
    "proxy_send_timeout",
    "proxy_read_timeout",
)


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
    for name in _COLUMNS:
        if _has_column("proxy_hosts", name):
            continue
        op.add_column(
            "proxy_hosts",
            sa.Column(name, sa.Integer(), nullable=False, server_default="60"),
        )
        # The default was only needed to backfill existing rows; the app always
        # sends an explicit value.
        op.alter_column(
            "proxy_hosts",
            name,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    for name in _COLUMNS:
        if _has_column("proxy_hosts", name):
            op.drop_column("proxy_hosts", name)
