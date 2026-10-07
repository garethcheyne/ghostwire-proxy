"""API keys for scripts and AI agents (MCP)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-07

Scoped API keys, sent as `Authorization: Bearer gwp_<prefix>_<secret>`. Only the
prefix and a SHA-256 hash of the key are stored.

Idempotent for the same reason as 0011-0016 — migration 0001 builds the baseline
from the live models with create_all(), so on a new install the table exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table("api_keys")


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"], unique=True)
    op.create_index("ix_api_keys_created_by", "api_keys", ["created_by"])


def downgrade() -> None:
    if not _has_table():
        return
    op.drop_index("ix_api_keys_created_by", table_name="api_keys")
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_table("api_keys")
