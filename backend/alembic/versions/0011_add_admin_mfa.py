"""add TOTP MFA columns to admin users

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-09

Auth-wall visitors have had TOTP since the beginning (local_auth_users), but the
admin portal itself — the account that can rewrite every proxy host, read every
traffic log and restore every backup — was password-only. These columns mirror
the local_auth_users ones exactly so both flows can share the same shape.

totp_secret and totp_backup_codes are Fernet-encrypted at rest, never stored raw.

Written idempotently on purpose. Migration 0001 builds the baseline with
`Base.metadata.create_all()` against the *live* models, so on a fresh database
these columns already exist by the time this runs, while on an existing database
they do not. Guarding on the actual schema is the only thing that works for both.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("totp_enabled", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("totp_verified", sa.Column("totp_verified", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("totp_secret", sa.Column("totp_secret", sa.Text(), nullable=True)),
    ("totp_backup_codes", sa.Column("totp_backup_codes", sa.Text(), nullable=True)),
    ("totp_enrolled_at", sa.Column("totp_enrolled_at", sa.DateTime(timezone=True), nullable=True)),
)


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns("users")}


def upgrade() -> None:
    existing = _existing_columns()
    for name, column in _COLUMNS:
        if name not in existing:
            op.add_column("users", column)


def downgrade() -> None:
    existing = _existing_columns()
    for name, _ in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("users", name)
