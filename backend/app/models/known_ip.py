"""
Operator-supplied identity for IP addresses.

GeoIP and enrichment tell you where an address is and who owns the netblock.
They cannot tell you that 203.86.201.144 is "Head office" or that a particular
datacenter IP is your own monitoring. That knowledge only exists in the
operator's head, and without somewhere to put it every grid shows a wall of
anonymous numbers.
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, Index
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class KnownIp(Base):
    __tablename__ = "known_ips"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Exact address. CIDR ranges are a deliberate follow-up: exact matching
    # keeps the grid annotation lookup a single indexed hit per request.
    ip_address = Column(String(45), unique=True, nullable=False, index=True)

    # What to show instead of the bare address.
    label = Column(String(255), nullable=False)
    # What kind of thing this is: office, staff, vendor, monitoring, cdn, scanner...
    category = Column(String(50), nullable=True, index=True)

    # Which set it belongs to, e.g. "Microsoft Dataverse". Distinct from
    # category: a category says what an address is, a group ties many addresses
    # together so a service published across dozens of ranges reads as one thing.
    # Named group_name because "group" is a reserved word in SQL.
    group_name = Column(String(100), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    # Marks an address you recognise as benign. Purely informational — it does
    # not grant any bypass; the WAF's trusted-IP list is a separate, deliberate
    # security control and must stay that way.
    trusted = Column(Boolean, default=False, nullable=False)

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_known_ips_category_label", "category", "label"),
    )
