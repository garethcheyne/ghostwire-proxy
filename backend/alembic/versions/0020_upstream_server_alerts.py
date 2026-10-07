"""per-backend-server down/recovered alerts

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08

upstream_servers gains what the per-server alerts last announced
(alert_status) and when the last down alert went out (alert_down_at, for flap
protection). Both start NULL, so no server is announced until it has first been
seen up: an upgrade never sends a burst of alerts for servers that were already
down.

upstream_server_events keeps a short history of servers going down and coming
back for the host's Backends section.

Idempotent for the same reason as 0011-0019: migration 0001 builds the
baseline from the live models with create_all().
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

EVENTS = "upstream_server_events"


def _server_columns() -> list[sa.Column]:
    return [
        sa.Column("alert_status", sa.String(10), nullable=True),
        sa.Column("alert_down_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    existing = {c["name"] for c in _inspector().get_columns("upstream_servers")}
    for column in _server_columns():
        if column.name not in existing:
            op.add_column("upstream_servers", column)

    if not _inspector().has_table(EVENTS):
        op.create_table(
            EVENTS,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("proxy_host_id", sa.String(36), sa.ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("upstream_server_id", sa.String(36), nullable=True),
            sa.Column("server", sa.String(300), nullable=False),
            sa.Column("event", sa.String(20), nullable=False),
            sa.Column("alert", sa.String(20), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("healthy", sa.Integer(), nullable=True),
            sa.Column("total", sa.Integer(), nullable=True),
            sa.Column("auto_down", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{EVENTS}_proxy_host_id ON {EVENTS} (proxy_host_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{EVENTS}_created_at ON {EVENTS} (created_at)")


def downgrade() -> None:
    if _inspector().has_table(EVENTS):
        op.drop_table(EVENTS)
    existing = {c["name"] for c in _inspector().get_columns("upstream_servers")}
    for column in reversed(_server_columns()):
        if column.name in existing:
            op.drop_column("upstream_servers", column.name)
