"""Pydantic schemas for honeypot traps and IP enrichment."""

from datetime import datetime

from pydantic import BaseModel, Field

# ── Honeypot Traps ─────────────────────────────────────────────


class HoneypotTrapCreate(BaseModel):
    path: str = Field(..., max_length=500, description="URL path to trap (e.g. /wp-login.php)")
    name: str = Field(..., max_length=255)
    description: str | None = None
    trap_type: str = Field(default="generic", pattern="^(wordpress|phpmyadmin|admin|api|generic)$")
    response_code: int = Field(default=200, ge=100, le=599)
    response_body: str | None = None
    severity: str = Field(default="high", pattern="^(low|medium|high|critical)$")
    auto_block: bool = True
    enabled: bool = True
    proxy_host_id: str | None = None  # None = all hosts


class HoneypotTrapUpdate(BaseModel):
    path: str | None = Field(None, max_length=500)
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    trap_type: str | None = Field(None, pattern="^(wordpress|phpmyadmin|admin|api|generic)$")
    response_code: int | None = Field(None, ge=100, le=599)
    response_body: str | None = None
    severity: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    auto_block: bool | None = None
    enabled: bool | None = None
    proxy_host_id: str | None = None


class HoneypotTrapResponse(BaseModel):
    id: str
    path: str
    name: str
    description: str | None
    trap_type: str
    response_code: int
    response_body: str | None
    severity: str
    auto_block: bool
    enabled: bool
    proxy_host_id: str | None
    hit_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Honeypot Hits ──────────────────────────────────────────────


class HoneypotHitResponse(BaseModel):
    id: str
    trap_id: str
    trap_path: str
    client_ip: str
    request_method: str | None
    request_uri: str | None
    request_headers: str | None
    request_body: str | None
    user_agent: str | None
    host: str | None
    referer: str | None
    country_code: str | None
    country_name: str | None
    action_taken: str
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── IP Enrichment ──────────────────────────────────────────────


class IpEnrichmentResponse(BaseModel):
    id: str
    ip_address: str
    country_code: str | None
    country_name: str | None
    city: str | None
    region: str | None
    latitude: str | None
    longitude: str | None
    timezone: str | None
    isp: str | None
    org: str | None
    asn: str | None
    as_name: str | None
    reverse_dns: str | None
    abuse_score: int | None
    abuse_reports: int | None
    abuse_last_reported: datetime | None
    is_tor: bool | None
    is_proxy: bool | None
    is_vpn: bool | None
    is_datacenter: bool | None
    is_crawler: bool | None
    raw_data: str | None
    enriched_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IpLookupRequest(BaseModel):
    ip: str = Field(..., max_length=45)


# ── Honeypot Stats ─────────────────────────────────────────────


class HoneypotStatsResponse(BaseModel):
    total_traps: int
    active_traps: int
    total_hits: int
    hits_today: int
    hits_this_week: int
    unique_ips: int
    auto_blocked: int
    top_traps: list[dict]  # [{path, hit_count}]
    top_attackers: list[dict]  # [{ip, hits, country}]
    recent_hits: list[dict]  # [{ip, path, timestamp, country}]
