from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class WafRuleSetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True


class WafRuleSetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class WafRuleSetResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WafRuleCreate(BaseModel):
    rule_set_id: Optional[str] = None
    proxy_host_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: str
    pattern: str
    severity: str = "medium"
    action: str = "log"
    enabled: bool = True
    is_lua: bool = True

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid = ('sqli', 'xss', 'path_traversal', 'rce', 'scanner', 'custom')
        if v not in valid:
            raise ValueError(f'Category must be one of: {", ".join(valid)}')
        return v

    @field_validator('severity')
    @classmethod
    def validate_severity(cls, v: str) -> str:
        valid = ('low', 'medium', 'high', 'critical')
        if v not in valid:
            raise ValueError(f'Severity must be one of: {", ".join(valid)}')
        return v

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid = ('log', 'block', 'blocklist')
        if v not in valid:
            raise ValueError(f'Action must be one of: {", ".join(valid)}')
        return v


class WafRuleUpdate(BaseModel):
    proxy_host_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    pattern: Optional[str] = None
    severity: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None


class WafRuleResponse(BaseModel):
    id: str
    rule_set_id: Optional[str]
    proxy_host_id: Optional[str]
    name: str
    description: Optional[str]
    category: str
    pattern: str
    severity: str
    action: str
    enabled: bool
    is_lua: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ThreatEventResponse(BaseModel):
    id: str
    proxy_host_id: Optional[str]
    client_ip: str
    rule_id: Optional[str]
    rule_name: Optional[str]
    category: Optional[str]
    severity: Optional[str]
    action_taken: Optional[str]
    request_method: Optional[str]
    request_uri: Optional[str]
    matched_payload: Optional[str]
    user_agent: Optional[str]
    host: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class ThreatActorResponse(BaseModel):
    id: str
    ip_address: str
    total_events: int
    threat_score: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    current_status: str
    temp_block_until: Optional[datetime]
    perm_blocked_at: Optional[datetime]
    firewall_banned_at: Optional[datetime]
    country_code: Optional[str]
    country_name: Optional[str]
    tags: Optional[list[str]] = None
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return []
        return v


class ThreatActorUpdate(BaseModel):
    current_status: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None

    @field_validator('current_status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ('monitored', 'warned', 'temp_blocked', 'perm_blocked', 'firewall_banned')
            if v not in valid:
                raise ValueError(f'Status must be one of: {", ".join(valid)}')
        return v


class ThreatThresholdCreate(BaseModel):
    name: str
    events_count: Optional[int] = None
    time_window_minutes: Optional[int] = None
    threat_score: Optional[int] = None
    response_action: str
    temp_block_duration_minutes: Optional[int] = None
    enabled: bool = True
    priority: int = 0

    @field_validator('response_action')
    @classmethod
    def validate_response_action(cls, v: str) -> str:
        valid = ('warn', 'temp_block', 'perm_block', 'firewall_ban')
        if v not in valid:
            raise ValueError(f'Response action must be one of: {", ".join(valid)}')
        return v


class ThreatThresholdUpdate(BaseModel):
    name: Optional[str] = None
    events_count: Optional[int] = None
    time_window_minutes: Optional[int] = None
    threat_score: Optional[int] = None
    response_action: Optional[str] = None
    temp_block_duration_minutes: Optional[int] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class ThreatThresholdResponse(BaseModel):
    id: str
    name: str
    events_count: Optional[int]
    time_window_minutes: Optional[int]
    threat_score: Optional[int]
    response_action: str
    temp_block_duration_minutes: Optional[int]
    enabled: bool
    priority: int

    class Config:
        from_attributes = True


class ThreatStatsResponse(BaseModel):
    total_events: int
    events_today: int
    events_this_week: int
    total_actors: int
    blocked_actors: int
    top_categories: list[dict]
    top_actors: list[dict]
    severity_breakdown: dict
