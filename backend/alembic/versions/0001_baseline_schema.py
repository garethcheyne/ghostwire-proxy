"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-04-05

Baseline migration that establishes all tables.
- Fresh DB: creates all 43 tables from model metadata.
- Existing DB: checkfirst=True skips tables that already exist.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import all models so Base.metadata is fully populated
    import app.models  # noqa: F401
    from app.core.database import Base

    # create_all with checkfirst=True:
    #   - On fresh DB: creates all tables
    #   - On existing DB: skips tables that already exist (safe no-op)
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Cannot safely downgrade from baseline — would destroy all data
    pass
