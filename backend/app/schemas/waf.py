from datetime import datetime

from pydantic import BaseModel, field_validator


class WafRuleSetCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True


class WafRuleSetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class WafRuleSetResponse(BaseModel):
    id: str
    name: str
    description: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WafRuleCreate(BaseModel):
    rule_set_id: str | None = None
    proxy_host_id: str | None = None
    name: str
    description: str | None = None
    category: str
    pattern: str
    severity: str = "medium"
    action: str = "log"
    enabled: bool = True
    is_lua: bool = True

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid = (
            'sqli',
            'xss',
            'path_traversal',
            'rce',
            'scanner',
            'probe',
            'custom',
            'protocol',
            'file_upload',
            'injection',
            'recon',
            'dos',
            'sensitive_data',
        )
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
    proxy_host_id: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    pattern: str | None = None
    severity: str | None = None
    action: str | None = None
    enabled: bool | None = None


class WafRuleResponse(BaseModel):
    id: str
    rule_set_id: str | None
    proxy_host_id: str | None
    name: str
    description: str | None
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
    proxy_host_id: str | None
    client_ip: str
    rule_id: str | None
    rule_name: str | None
    category: str | None
    severity: str | None
    action_taken: str | None
    request_method: str | None
    request_uri: str | None
    matched_payload: str | None
    user_agent: str | None
    host: str | None
    timestamp: datetime

    class Config:
        from_attributes = True


class ThreatActorResponse(BaseModel):
    id: str
    ip_address: str
    total_events: int
    threat_score: int
    first_seen: datetime | None
    last_seen: datetime | None
    current_status: str
    temp_block_until: datetime | None
    perm_blocked_at: datetime | None
    firewall_banned_at: datetime | None
    country_code: str | None
    country_name: str | None
    tags: list[str] | None = None
    notes: str | None
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
    current_status: str | None = None
    tags: list[str] | None = None
    notes: str | None = None

    @field_validator('current_status')
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            valid = ('monitored', 'warned', 'temp_blocked', 'perm_blocked', 'firewall_banned')
            if v not in valid:
                raise ValueError(f'Status must be one of: {", ".join(valid)}')
        return v


class ThreatThresholdCreate(BaseModel):
    name: str
    events_count: int | None = None
    time_window_minutes: int | None = None
    threat_score: int | None = None
    response_action: str
    temp_block_duration_minutes: int | None = None
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
    name: str | None = None
    events_count: int | None = None
    time_window_minutes: int | None = None
    threat_score: int | None = None
    response_action: str | None = None
    temp_block_duration_minutes: int | None = None
    enabled: bool | None = None
    priority: int | None = None


class ThreatThresholdResponse(BaseModel):
    id: str
    name: str
    events_count: int | None
    time_window_minutes: int | None
    threat_score: int | None
    response_action: str
    temp_block_duration_minutes: int | None
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
