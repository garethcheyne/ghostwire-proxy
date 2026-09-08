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


def upgrade() -> None:
    op.add_column(
        "proxy_hosts",
        sa.Column("cdn_provider", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.alter_column("proxy_hosts", "cdn_provider",
                    existing_type=sa.String(length=20), existing_nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_column("proxy_hosts", "cdn_provider")
