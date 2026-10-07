"""allow-list for OAuth sign-in on auth walls

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08

Two nullable JSON columns on auth_walls: exact email addresses and email
domains allowed through an OAuth provider. Both empty keeps the previous
behaviour (any account the provider vouches for), so existing walls keep
working; the admin UI warns about walls left open that way.

Idempotent for the same reason as 0011-0018: migration 0001 builds the
baseline from the live models with create_all().
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_COLUMNS = ("allowed_emails", "allowed_email_domains")


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("auth_walls")}


def upgrade() -> None:
    existing = _columns()
    for name in _COLUMNS:
        if name not in existing:
            op.add_column("auth_walls", sa.Column(name, sa.JSON(), nullable=True))


def downgrade() -> None:
    existing = _columns()
    for name in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("auth_walls", name)
