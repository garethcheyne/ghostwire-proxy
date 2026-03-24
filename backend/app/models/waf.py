from sqlalchemy import Column, String, DateTime, Text, Integer, Index, Boolean, ForeignKey
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class WafRuleSet(Base):
    __tablename__ = "waf_rule_sets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    preset_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class WafRule(Base):
    __tablename__ = "waf_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_set_id = Column(String(36), nullable=True, index=True)
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)  # sqli, xss, path_traversal, rce, scanner
    pattern = Column(Text, nullable=False)
    severity = Column(String(20), default="medium")  # low, medium, high, critical
    action = Column(String(20), default="log")  # log, block, blocklist
    enabled = Column(Boolean, default=True, nullable=False)
    is_lua = Column(Boolean, default=True, nullable=False)  # True=Lua, False=ModSecurity
    preset_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_waf_rules_category_enabled', 'category', 'enabled'),
    )


class ThreatEvent(Base):
    __tablename__ = "threat_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), nullable=True, index=True)
    client_ip = Column(String(45), nullable=False, index=True)
    rule_id = Column(String(36), nullable=True)
    rule_name = Column(String(255), nullable=True)
    category = Column(String(50), nullable=True, index=True)
    severity = Column(String(20), nullable=True)
    action_taken = Column(String(20), nullable=True)  # logged, blocked, blocklisted
    request_method = Column(String(10), nullable=True)
    request_uri = Column(Text, nullable=True)
    request_headers = Column(Text, nullable=True)  # JSON
    matched_payload = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    host = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index('idx_threat_events_ip_timestamp', 'client_ip', 'timestamp'),
    )


class ThreatActor(Base):
    __tablename__ = "threat_actors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ip_address = Column(String(45), unique=True, nullable=False, index=True)
    total_events = Column(Integer, default=0)
    threat_score = Column(Integer, default=0)
    first_seen = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    current_status = Column(String(20), default="monitored")  # monitored, warned, temp_blocked, perm_blocked, firewall_banned
    temp_block_until = Column(DateTime(timezone=True), nullable=True)
    perm_blocked_at = Column(DateTime(timezone=True), nullable=True)
    firewall_banned_at = Column(DateTime(timezone=True), nullable=True)
    country_code = Column(String(5), nullable=True)
    country_name = Column(String(100), nullable=True)
    tags = Column(Text, nullable=True)  # JSON array of tag strings
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ThreatThreshold(Base):
    __tablename__ = "threat_thresholds"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    events_count = Column(Integer, nullable=True)
    time_window_minutes = Column(Integer, nullable=True)
    threat_score = Column(Integer, nullable=True)
    response_action = Column(String(20), nullable=False)  # warn, temp_block, perm_block, firewall_ban
    temp_block_duration_minutes = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    preset_id = Column(String(100), nullable=True, index=True)
    priority = Column(Integer, default=0)
