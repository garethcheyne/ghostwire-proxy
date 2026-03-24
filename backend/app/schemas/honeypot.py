"""Pydantic schemas for honeypot traps and IP enrichment."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Honeypot Traps ─────────────────────────────────────────────

class HoneypotTrapCreate(BaseModel):
    path: str = Field(..., max_length=500, description="URL path to trap (e.g. /wp-login.php)")
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    trap_type: str = Field(default="generic", pattern="^(wordpress|phpmyadmin|admin|api|generic)$")
    response_code: int = Field(default=200, ge=100, le=599)
    response_body: Optional[str] = None
    severity: str = Field(default="high", pattern="^(low|medium|high|critical)$")
    auto_block: bool = True
    enabled: bool = True
    proxy_host_id: Optional[str] = None  # None = all hosts


class HoneypotTrapUpdate(BaseModel):
    path: Optional[str] = Field(None, max_length=500)
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    trap_type: Optional[str] = Field(None, pattern="^(wordpress|phpmyadmin|admin|api|generic)$")
    response_code: Optional[int] = Field(None, ge=100, le=599)
    response_body: Optional[str] = None
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    auto_block: Optional[bool] = None
    enabled: Optional[bool] = None
    proxy_host_id: Optional[str] = None


class HoneypotTrapResponse(BaseModel):
    id: str
    path: str
    name: str
    description: Optional[str]
    trap_type: str
    response_code: int
    response_body: Optional[str]
    severity: str
    auto_block: bool
    enabled: bool
    proxy_host_id: Optional[str]
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
    request_method: Optional[str]
    request_uri: Optional[str]
    request_headers: Optional[str]
    request_body: Optional[str]
    user_agent: Optional[str]
    host: Optional[str]
    referer: Optional[str]
    country_code: Optional[str]
    country_name: Optional[str]
    action_taken: str
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── IP Enrichment ──────────────────────────────────────────────

class IpEnrichmentResponse(BaseModel):
    id: str
    ip_address: str
    country_code: Optional[str]
    country_name: Optional[str]
    city: Optional[str]
    region: Optional[str]
    latitude: Optional[str]
    longitude: Optional[str]
    timezone: Optional[str]
    isp: Optional[str]
    org: Optional[str]
    asn: Optional[str]
    as_name: Optional[str]
    reverse_dns: Optional[str]
    abuse_score: Optional[int]
    abuse_reports: Optional[int]
    abuse_last_reported: Optional[datetime]
    is_tor: Optional[bool]
    is_proxy: Optional[bool]
    is_vpn: Optional[bool]
    is_datacenter: Optional[bool]
    is_crawler: Optional[bool]
    raw_data: Optional[str]
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
