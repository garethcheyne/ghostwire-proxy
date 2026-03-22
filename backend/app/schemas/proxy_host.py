from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class UpstreamServerCreate(BaseModel):
    host: str
    port: int
    weight: int = 1
    max_fails: int = 3
    fail_timeout: int = 30
    enabled: bool = True

    @field_validator('port')
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v


class UpstreamServerResponse(BaseModel):
    id: str
    proxy_host_id: str
    host: str
    port: int
    weight: int
    max_fails: int
    fail_timeout: int
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# ProxyLocation Schemas
# ============================================================================

class ProxyLocationBase(BaseModel):
    path: str
    match_type: str = "prefix"  # prefix, exact, regex, regex_case_insensitive
    priority: int = 0

    forward_scheme: str = "http"
    forward_host: str
    forward_port: int

    websockets_support: bool = False

    # Caching
    cache_enabled: bool = False
    cache_valid: Optional[str] = None
    cache_bypass: Optional[str] = None

    # Rate limiting
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 100
    rate_limit_period: str = "1s"
    rate_limit_burst: int = 50

    # Headers
    custom_headers: Optional[dict[str, str]] = None
    proxy_headers: Optional[dict[str, str]] = None
    hide_headers: Optional[list[str]] = None

    # Timeouts
    proxy_connect_timeout: int = 60
    proxy_send_timeout: int = 60
    proxy_read_timeout: int = 60

    advanced_config: Optional[str] = None
    enabled: bool = True

    @field_validator('forward_port')
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v

    @field_validator('forward_scheme')
    @classmethod
    def scheme_valid(cls, v: str) -> str:
        if v not in ('http', 'https'):
            raise ValueError('Scheme must be http or https')
        return v

    @field_validator('match_type')
    @classmethod
    def match_type_valid(cls, v: str) -> str:
        if v not in ('prefix', 'exact', 'regex', 'regex_case_insensitive'):
            raise ValueError('Match type must be prefix, exact, regex, or regex_case_insensitive')
        return v


class ProxyLocationCreate(ProxyLocationBase):
    pass


class ProxyLocationUpdate(BaseModel):
    path: Optional[str] = None
    match_type: Optional[str] = None
    priority: Optional[int] = None

    forward_scheme: Optional[str] = None
    forward_host: Optional[str] = None
    forward_port: Optional[int] = None

    websockets_support: Optional[bool] = None

    cache_enabled: Optional[bool] = None
    cache_valid: Optional[str] = None
    cache_bypass: Optional[str] = None

    rate_limit_enabled: Optional[bool] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_period: Optional[str] = None
    rate_limit_burst: Optional[int] = None

    custom_headers: Optional[dict[str, str]] = None
    proxy_headers: Optional[dict[str, str]] = None
    hide_headers: Optional[list[str]] = None

    proxy_connect_timeout: Optional[int] = None
    proxy_send_timeout: Optional[int] = None
    proxy_read_timeout: Optional[int] = None

    advanced_config: Optional[str] = None
    enabled: Optional[bool] = None


class ProxyLocationResponse(BaseModel):
    id: str
    proxy_host_id: str
    path: str
    match_type: str
    priority: int

    forward_scheme: str
    forward_host: str
    forward_port: int

    websockets_support: bool

    cache_enabled: bool
    cache_valid: Optional[str]
    cache_bypass: Optional[str]

    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_period: str
    rate_limit_burst: int

    custom_headers: Optional[dict[str, str]]
    proxy_headers: Optional[dict[str, str]]
    hide_headers: Optional[list[str]]

    proxy_connect_timeout: int
    proxy_send_timeout: int
    proxy_read_timeout: int

    advanced_config: Optional[str]
    enabled: bool

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LocationReorderItem(BaseModel):
    id: str
    priority: int


class LocationReorderRequest(BaseModel):
    locations: list[LocationReorderItem]


# ============================================================================
# ProxyHost Schemas
# ============================================================================

class ProxyHostBase(BaseModel):
    domain_names: list[str]
    forward_scheme: str = "http"
    forward_host: str
    forward_port: int

    ssl_enabled: bool = False
    ssl_force: bool = False
    certificate_id: Optional[str] = None

    http2_support: bool = True
    hsts_enabled: bool = False
    hsts_subdomains: bool = False
    websockets_support: bool = True
    block_exploits: bool = True

    access_list_id: Optional[str] = None
    auth_wall_id: Optional[str] = None

    # Location-level advanced config
    advanced_config: Optional[str] = None

    # Server-level advanced config
    server_advanced_config: Optional[str] = None

    # Server-level settings
    client_max_body_size: str = "100m"
    proxy_buffering: bool = True
    proxy_buffer_size: str = "4k"
    proxy_buffers: str = "8 4k"

    # Caching
    cache_enabled: bool = False
    cache_valid: Optional[str] = None
    cache_bypass: Optional[str] = None

    # Rate limiting
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 100
    rate_limit_period: str = "1s"
    rate_limit_burst: int = 50

    # Custom error pages
    custom_error_pages: Optional[dict[str, str]] = None

    traffic_logging_enabled: bool = False
    enabled: bool = True

    @field_validator('forward_port')
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v

    @field_validator('forward_scheme')
    @classmethod
    def scheme_valid(cls, v: str) -> str:
        if v not in ('http', 'https'):
            raise ValueError('Scheme must be http or https')
        return v


class ProxyHostCreate(ProxyHostBase):
    upstream_servers: Optional[list[UpstreamServerCreate]] = None
    locations: Optional[list[ProxyLocationCreate]] = None


class ProxyHostUpdate(BaseModel):
    domain_names: Optional[list[str]] = None
    forward_scheme: Optional[str] = None
    forward_host: Optional[str] = None
    forward_port: Optional[int] = None

    ssl_enabled: Optional[bool] = None
    ssl_force: Optional[bool] = None
    certificate_id: Optional[str] = None

    http2_support: Optional[bool] = None
    hsts_enabled: Optional[bool] = None
    hsts_subdomains: Optional[bool] = None
    websockets_support: Optional[bool] = None
    block_exploits: Optional[bool] = None

    access_list_id: Optional[str] = None
    auth_wall_id: Optional[str] = None

    advanced_config: Optional[str] = None
    server_advanced_config: Optional[str] = None

    client_max_body_size: Optional[str] = None
    proxy_buffering: Optional[bool] = None
    proxy_buffer_size: Optional[str] = None
    proxy_buffers: Optional[str] = None

    cache_enabled: Optional[bool] = None
    cache_valid: Optional[str] = None
    cache_bypass: Optional[str] = None

    rate_limit_enabled: Optional[bool] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_period: Optional[str] = None
    rate_limit_burst: Optional[int] = None

    custom_error_pages: Optional[dict[str, str]] = None

    traffic_logging_enabled: Optional[bool] = None
    enabled: Optional[bool] = None


class ProxyHostResponse(BaseModel):
    id: str
    domain_names: list[str]
    forward_scheme: str
    forward_host: str
    forward_port: int

    ssl_enabled: bool
    ssl_force: bool
    certificate_id: Optional[str]

    http2_support: bool
    hsts_enabled: bool
    hsts_subdomains: bool
    websockets_support: bool
    block_exploits: bool

    access_list_id: Optional[str]
    auth_wall_id: Optional[str]

    advanced_config: Optional[str]
    server_advanced_config: Optional[str]

    client_max_body_size: str
    proxy_buffering: bool
    proxy_buffer_size: str
    proxy_buffers: str

    cache_enabled: bool
    cache_valid: Optional[str]
    cache_bypass: Optional[str]

    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_period: str
    rate_limit_burst: int

    custom_error_pages: Optional[dict[str, str]]

    traffic_logging_enabled: bool
    enabled: bool

    upstream_servers: list[UpstreamServerResponse] = []
    locations: list[ProxyLocationResponse] = []

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
