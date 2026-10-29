import re
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.services.load_balancing import (
    HEALTH_CHECK_TYPES,
    LB_METHODS,
    normalize_upstream_host,
    validate_health_check_path,
)


def _check_port(v: int | None) -> int | None:
    if v is not None and not 1 <= v <= 65535:
        raise ValueError('Port must be between 1 and 65535')
    return v


def _check_server_fields(model):
    """Range checks shared by every upstream-server schema (None = not sent)."""
    if model.weight is not None and not 1 <= model.weight <= 100:
        raise ValueError('Weight must be between 1 and 100')
    if model.max_fails is not None and not 0 <= model.max_fails <= 100:
        raise ValueError('Max fails must be between 0 and 100 (0 turns failure counting off)')
    if model.fail_timeout is not None and not 1 <= model.fail_timeout <= 3600:
        raise ValueError('Fail timeout must be between 1 and 3600 seconds')
    if model.max_conns is not None and not 1 <= model.max_conns <= 100000:
        raise ValueError('Max connections must be between 1 and 100000, or empty for no limit')
    return model


class UpstreamServerBase(BaseModel):
    host: str
    port: int
    weight: int = 1
    max_fails: int = 3
    fail_timeout: int = 30
    backup: bool = False
    down: bool = False
    max_conns: int | None = None
    enabled: bool = True

    @field_validator('host')
    @classmethod
    def host_valid(cls, v: str) -> str:
        return normalize_upstream_host(v)

    @field_validator('port')
    @classmethod
    def port_range(cls, v: int) -> int:
        return _check_port(v)

    @model_validator(mode='after')
    def ranges(self):
        return _check_server_fields(self)


class UpstreamServerCreate(UpstreamServerBase):
    pass


class UpstreamServerUpsert(UpstreamServerBase):
    """A server in a full-list replace: rows with an id are updated (keeping
    their health history), rows without one are added, and saved rows missing
    from the list are removed."""

    id: str | None = None


class UpstreamServerUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    weight: int | None = None
    max_fails: int | None = None
    fail_timeout: int | None = None
    backup: bool | None = None
    down: bool | None = None
    max_conns: int | None = None
    enabled: bool | None = None

    @field_validator('host')
    @classmethod
    def host_valid(cls, v: str | None) -> str | None:
        return None if v is None else normalize_upstream_host(v)

    @field_validator('port')
    @classmethod
    def port_range(cls, v: int | None) -> int | None:
        return _check_port(v)

    @model_validator(mode='after')
    def ranges(self):
        return _check_server_fields(self)


class UpstreamServerResponse(BaseModel):
    id: str
    proxy_host_id: str
    host: str
    port: int
    weight: int
    max_fails: int
    fail_timeout: int
    backup: bool = False
    down: bool = False
    max_conns: int | None = None
    enabled: bool
    # Health, from the background loop (or a manual "Check now")
    last_check_at: datetime | None = None
    last_status: str = "unknown"
    last_error: str | None = None
    last_latency_ms: int | None = None
    auto_down: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class LoadBalancingSettings(BaseModel):
    """Host-level load-balancing fields, shared by create and the preview."""

    lb_method: str = "round_robin"
    upstream_keepalive: int = 32
    health_check_type: str = "http"
    health_check_path: str = "/"
    health_check_timeout: int = 5
    lb_auto_down: bool = False

    @field_validator('lb_method')
    @classmethod
    def method_valid(cls, v: str) -> str:
        return _check_lb_method(v)

    @field_validator('upstream_keepalive')
    @classmethod
    def keepalive_range(cls, v: int) -> int:
        return _check_keepalive(v)

    @field_validator('health_check_type')
    @classmethod
    def check_type_valid(cls, v: str) -> str:
        return _check_health_type(v)

    @field_validator('health_check_path')
    @classmethod
    def check_path_valid(cls, v: str) -> str:
        return validate_health_check_path(v)

    @field_validator('health_check_timeout')
    @classmethod
    def check_timeout_range(cls, v: int) -> int:
        return _check_health_timeout(v)


def _check_lb_method(v):
    if v is not None and v not in LB_METHODS:
        raise ValueError(f"Balancing method must be one of: {', '.join(LB_METHODS)}")
    return v


def _check_keepalive(v):
    if v is not None and not 0 <= v <= 1024:
        raise ValueError('Upstream keepalive must be between 0 (off) and 1024')
    return v


def _check_health_type(v):
    if v is not None and v not in HEALTH_CHECK_TYPES:
        raise ValueError('Health check type must be http or tcp')
    return v


def _check_health_timeout(v):
    if v is not None and not 1 <= v <= 30:
        raise ValueError('Health check timeout must be between 1 and 30 seconds')
    return v


class UpstreamPreviewRequest(LoadBalancingSettings):
    """What the editor has on screen, rendered without saving anything."""

    host_id: str | None = None
    forward_scheme: str = "http"
    websockets_support: bool = True
    servers: list[UpstreamServerUpsert] = []


class UpstreamPreviewResponse(BaseModel):
    upstream_block: str
    location_directives: str
    errors: list[str]
    warnings: list[str]


class UpstreamCheckResult(BaseModel):
    id: str
    host: str
    port: int
    status: str
    latency_ms: int | None
    error: str | None


class UpstreamServerEventResponse(BaseModel):
    """A backend going down or coming back, and what happened to its alert."""

    id: str
    upstream_server_id: str | None = None
    server: str
    event: str  # down, recovered
    alert: str  # sent, held (flap protection), grouped (host-down alert covered it)
    error: str | None = None
    latency_ms: int | None = None
    healthy: int | None = None
    total: int | None = None
    auto_down: bool = False
    created_at: datetime | None = None

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
    cache_valid: str | None = None
    cache_bypass: str | None = None

    # Rate limiting
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 100
    rate_limit_period: str = "1s"
    rate_limit_burst: int = 50

    # Headers
    custom_headers: dict[str, str] | None = None
    proxy_headers: dict[str, str] | None = None
    hide_headers: list[str] | None = None

    # Timeouts
    proxy_connect_timeout: int = 60
    proxy_send_timeout: int = 60
    proxy_read_timeout: int = 60

    advanced_config: str | None = None
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
    path: str | None = None
    match_type: str | None = None
    priority: int | None = None

    forward_scheme: str | None = None
    forward_host: str | None = None
    forward_port: int | None = None

    websockets_support: bool | None = None

    cache_enabled: bool | None = None
    cache_valid: str | None = None
    cache_bypass: str | None = None

    rate_limit_enabled: bool | None = None
    rate_limit_requests: int | None = None
    rate_limit_period: str | None = None
    rate_limit_burst: int | None = None

    custom_headers: dict[str, str] | None = None
    proxy_headers: dict[str, str] | None = None
    hide_headers: list[str] | None = None

    proxy_connect_timeout: int | None = None
    proxy_send_timeout: int | None = None
    proxy_read_timeout: int | None = None

    advanced_config: str | None = None
    enabled: bool | None = None


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
    cache_valid: str | None
    cache_bypass: str | None

    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_period: str
    rate_limit_burst: int

    custom_headers: dict[str, str] | None
    proxy_headers: dict[str, str] | None
    hide_headers: list[str] | None

    proxy_connect_timeout: int
    proxy_send_timeout: int
    proxy_read_timeout: int

    advanced_config: str | None
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


class ProxyHostBase(LoadBalancingSettings):
    domain_names: list[str]
    forward_scheme: str = "http"
    forward_host: str
    forward_port: int

    ssl_enabled: bool = False
    ssl_force: bool = False
    certificate_id: str | None = None

    http2_support: bool = True
    hsts_enabled: bool = False
    hsts_subdomains: bool = False
    websockets_support: bool = True
    block_exploits: bool = True

    access_list_id: str | None = None
    auth_wall_id: str | None = None

    # Location-level advanced config
    advanced_config: str | None = None

    # Server-level advanced config
    server_advanced_config: str | None = None

    # Server-level settings
    client_max_body_size: str = "100m"
    proxy_buffering: bool = True
    proxy_buffer_size: str = "4k"
    proxy_buffers: str = "8 4k"

    # Front-facing CDN/WAF, if any: none, cloudflare, imperva, generic
    cdn_provider: str = "none"

    # Timeouts for the default ("/") location
    proxy_connect_timeout: int = 60
    proxy_send_timeout: int = 60
    proxy_read_timeout: int = 60

    # Caching
    cache_enabled: bool = False
    cache_valid: str | None = None
    cache_bypass: str | None = None

    # Rate limiting
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 100
    rate_limit_period: str = "1s"
    rate_limit_burst: int = 50

    # Custom error pages
    custom_error_pages: dict[str, str] | None = None

    traffic_logging_enabled: bool = False
    honeypot_enabled: bool = False
    enabled: bool = True

    @field_validator('domain_names')
    @classmethod
    def validate_domain_names(cls, v: list[str]) -> list[str]:
        return _check_domain_names(v)

    @field_validator('forward_host')
    @classmethod
    def forward_host_valid(cls, v: str) -> str:
        return normalize_upstream_host(v)

    @field_validator('forward_port')
    @classmethod
    def port_range(cls, v: int) -> int:
        return _check_port(v)

    @field_validator('forward_scheme')
    @classmethod
    def scheme_valid(cls, v: str) -> str:
        return _check_scheme(v)


_DOMAIN_RE = re.compile(r'^(\*\.)?[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$')


def _check_domain_names(v):
    """Shared by create and update: the names go straight into server_name."""
    if v is None:
        return v
    if not v:
        raise ValueError('At least one domain name is required')
    for d in v:
        if not _DOMAIN_RE.match(d):
            raise ValueError(f'Invalid domain name: {d}')
    return v


def _check_scheme(v):
    if v is not None and v not in ('http', 'https'):
        raise ValueError('Scheme must be http or https')
    return v


class ProxyHostCreate(ProxyHostBase):
    upstream_servers: list[UpstreamServerCreate] | None = None
    locations: list[ProxyLocationCreate] | None = None


class ProxyHostUpdate(BaseModel):
    domain_names: list[str] | None = None
    forward_scheme: str | None = None
    forward_host: str | None = None
    forward_port: int | None = None

    ssl_enabled: bool | None = None
    ssl_force: bool | None = None
    certificate_id: str | None = None

    http2_support: bool | None = None
    hsts_enabled: bool | None = None
    hsts_subdomains: bool | None = None
    websockets_support: bool | None = None
    block_exploits: bool | None = None

    access_list_id: str | None = None
    auth_wall_id: str | None = None

    advanced_config: str | None = None
    server_advanced_config: str | None = None

    client_max_body_size: str | None = None
    proxy_buffering: bool | None = None
    proxy_buffer_size: str | None = None
    proxy_buffers: str | None = None

    cdn_provider: str | None = None

    proxy_connect_timeout: int | None = None
    proxy_send_timeout: int | None = None
    proxy_read_timeout: int | None = None

    cache_enabled: bool | None = None
    cache_valid: str | None = None
    cache_bypass: str | None = None

    rate_limit_enabled: bool | None = None
    rate_limit_requests: int | None = None
    rate_limit_period: str | None = None
    rate_limit_burst: int | None = None

    custom_error_pages: dict[str, str] | None = None

    traffic_logging_enabled: bool | None = None
    honeypot_enabled: bool | None = None
    enabled: bool | None = None

    # Load balancing
    lb_method: str | None = None
    upstream_keepalive: int | None = None
    health_check_type: str | None = None
    health_check_path: str | None = None
    health_check_timeout: int | None = None
    lb_auto_down: bool | None = None
    # When sent, replaces the host's upstream servers in one validated apply
    # ([] switches the host back to a single backend).
    upstream_servers: list[UpstreamServerUpsert] | None = None

    # The same checks as create, so an update can't hand nginx -t (or the
    # config) a bad name, host or port either.
    @field_validator('domain_names')
    @classmethod
    def validate_domain_names(cls, v: list[str] | None) -> list[str] | None:
        return _check_domain_names(v)

    @field_validator('forward_host')
    @classmethod
    def forward_host_valid(cls, v: str | None) -> str | None:
        return None if v is None else normalize_upstream_host(v)

    @field_validator('forward_port')
    @classmethod
    def port_range(cls, v: int | None) -> int | None:
        return _check_port(v)

    @field_validator('forward_scheme')
    @classmethod
    def scheme_valid(cls, v: str | None) -> str | None:
        return _check_scheme(v)

    @field_validator('lb_method')
    @classmethod
    def method_valid(cls, v: str | None) -> str | None:
        return _check_lb_method(v)

    @field_validator('upstream_keepalive')
    @classmethod
    def keepalive_range(cls, v: int | None) -> int | None:
        return _check_keepalive(v)

    @field_validator('health_check_type')
    @classmethod
    def check_type_valid(cls, v: str | None) -> str | None:
        return _check_health_type(v)

    @field_validator('health_check_timeout')
    @classmethod
    def check_timeout_range(cls, v: int | None) -> int | None:
        return _check_health_timeout(v)

    @field_validator('health_check_path')
    @classmethod
    def check_path_valid(cls, v: str | None) -> str | None:
        return None if v is None else validate_health_check_path(v)


class ProxyHostResponse(BaseModel):
    id: str
    domain_names: list[str]
    forward_scheme: str
    forward_host: str
    forward_port: int

    ssl_enabled: bool
    ssl_force: bool
    certificate_id: str | None

    http2_support: bool
    hsts_enabled: bool
    hsts_subdomains: bool
    websockets_support: bool
    block_exploits: bool

    access_list_id: str | None
    auth_wall_id: str | None

    advanced_config: str | None
    server_advanced_config: str | None

    client_max_body_size: str
    proxy_buffering: bool
    proxy_buffer_size: str
    proxy_buffers: str

    cdn_provider: str

    proxy_connect_timeout: int
    proxy_send_timeout: int
    proxy_read_timeout: int

    cache_enabled: bool
    cache_valid: str | None
    cache_bypass: str | None

    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_period: str
    rate_limit_burst: int

    custom_error_pages: dict[str, str] | None

    traffic_logging_enabled: bool
    honeypot_enabled: bool
    enabled: bool

    lb_method: str = "round_robin"
    upstream_keepalive: int = 32
    health_check_type: str = "http"
    health_check_path: str = "/"
    health_check_timeout: int = 5
    lb_auto_down: bool = False
    health_check_enabled: bool = True
    health_status: str = "unknown"
    health_checked_at: datetime | None = None
    health_error: str | None = None

    upstream_servers: list[UpstreamServerResponse] = []
    locations: list[ProxyLocationResponse] = []

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
