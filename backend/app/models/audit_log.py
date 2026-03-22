from sqlalchemy import Column, String, DateTime, Text, Index
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # User info (not a FK to allow logs to persist after user deletion)
    user_id = Column(String(36), nullable=True, index=True)
    email = Column(String(255), nullable=True)

    # Action
    action = Column(String(100), nullable=False, index=True)
    details = Column(Text, nullable=True)

    # Request info
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Timestamp
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index('idx_audit_logs_user_timestamp', 'user_id', 'timestamp'),
    )
