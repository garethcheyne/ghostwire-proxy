from sqlalchemy import Column, String, Text, DateTime
from datetime import datetime, timezone

from app.core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)

    # Metadata
    description = Column(String(500), nullable=True)

    # Timestamps
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
