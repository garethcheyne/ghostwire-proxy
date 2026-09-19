"""better auth for admin sign-in

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-19

Moves admin sign-in to Better Auth (run by the admin UI). Additive: `users` stays the user table
(Better Auth maps onto it) and keeps its password hashes, so the previous release still works after
a rollback. Each user's bcrypt hash is copied into `auth_account` as their 'credential' account,
so everyone keeps their password. Admin two-factor (users.totp_*) is untouched: the UI's Better
Auth plugin asks the API to check codes, so nobody re-enrols.

Written idempotently, like 0011: migration 0001 builds a fresh database from the live models, so
there these tables and columns already exist, while an existing database has none of them.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _user_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    columns = _user_columns()
    if "email_verified" not in columns:
        op.add_column(
            "users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    if "image" not in columns:
        op.add_column("users", sa.Column("image", sa.String(1000), nullable=True))
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    # Defaults in the database too, so rows Better Auth inserts (e.g. future SSO users) are valid.
    op.alter_column("users", "signin_count", existing_type=sa.Integer(), server_default="0")
    op.alter_column("users", "role", existing_type=sa.String(50), server_default="user")
    op.alter_column("users", "is_active", existing_type=sa.Boolean(), server_default=sa.true())
    # Two-factor flags: 0011 gave them defaults, but databases built by 0001 from the models don't
    # have them, and Better Auth refuses to start on required columns it can't fill.
    for name in ("totp_enabled", "totp_verified"):
        if name in columns:
            op.alter_column("users", name, existing_type=sa.Boolean(), server_default=sa.false())

    tables = _tables()
    if "auth_session" not in tables:
        op.create_table(
            "auth_session",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("token", sa.String(255), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ip_address", sa.String(255), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            *_timestamps(),
        )
    if "auth_account" not in tables:
        op.create_table(
            "auth_account",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("account_id", sa.String(255), nullable=False),
            sa.Column("provider_id", sa.String(255), nullable=False),
            sa.Column("password", sa.Text(), nullable=True),
            sa.Column("access_token", sa.Text(), nullable=True),
            sa.Column("refresh_token", sa.Text(), nullable=True),
            sa.Column("id_token", sa.Text(), nullable=True),
            sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scope", sa.Text(), nullable=True),
            *_timestamps(),
        )
    if "auth_verification" not in tables:
        op.create_table(
            "auth_verification",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("identifier", sa.String(255), nullable=False, index=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            *_timestamps(),
        )

    # Everyone keeps their password: Better Auth verifies these bcrypt hashes as they are.
    op.execute(
        """
        INSERT INTO auth_account (id, user_id, account_id, provider_id, password, created_at, updated_at)
        SELECT gen_random_uuid()::text, u.id, u.id, 'credential', u.password_hash, now(), now()
        FROM users u
        WHERE u.password_hash IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM auth_account a WHERE a.user_id = u.id AND a.provider_id = 'credential'
          )
        """
    )


def downgrade() -> None:
    # Passwords changed since the upgrade live only in auth_account; copy them back first.
    op.execute(
        """
        UPDATE users u SET password_hash = a.password
        FROM auth_account a
        WHERE a.user_id = u.id AND a.provider_id = 'credential' AND a.password IS NOT NULL
        """
    )
    tables = _tables()
    for name in ("auth_verification", "auth_account", "auth_session"):
        if name in tables:
            op.drop_table(name)
    op.alter_column("users", "signin_count", existing_type=sa.Integer(), server_default=None)
    op.alter_column("users", "role", existing_type=sa.String(50), server_default=None)
    op.alter_column("users", "is_active", existing_type=sa.Boolean(), server_default=None)
    columns = _user_columns()
    for name in ("image", "email_verified"):
        if name in columns:
            op.drop_column("users", name)
