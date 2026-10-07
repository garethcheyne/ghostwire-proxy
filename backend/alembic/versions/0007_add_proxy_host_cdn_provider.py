"""add cdn_provider to proxy_hosts

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-08

Records which CDN/WAF (if any) fronts each host, so the generated server block
can point nginx's real_ip module at the right header and recover the true
visitor IP instead of logging - and rate-limiting, geo-blocking and threat-
scoring - the CDN's own edge address.

Defaults to "none", which keeps the safe X-Forwarded-For behaviour for hosts
that are reached directly or via a LAN load balancer.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
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
    if _has_column("proxy_hosts", "cdn_provider"):
        return
    op.add_column(
        "proxy_hosts",
        sa.Column("cdn_provider", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.alter_column("proxy_hosts", "cdn_provider",
                    existing_type=sa.String(length=20), existing_nullable=False, server_default=None)


def downgrade() -> None:
    if _has_column("proxy_hosts", "cdn_provider"):
        op.drop_column("proxy_hosts", "cdn_provider")
