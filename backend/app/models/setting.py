from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text

from app.core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)

    # Metadata
    description = Column(String(500), nullable=True)

    # Timestamps
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
