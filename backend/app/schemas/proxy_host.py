import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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


# ── Values written into nginx config ─────────────────────────────────────────
# Each of these lands in a generated server block as a bare token (or inside
# double quotes), so a `;`, `{`, `}`, quote, `#` or newline in it would end the
# directive and let the rest of the value add directives of its own, Lua
# included. `nginx -t` only checks syntax, so it would not catch that. Every
# value is held to the shape its directive takes. (advanced_config and
# server_advanced_config are raw nginx on purpose and are not checked here.)

_LOCATION_PATH_RE = re.compile(r'^[^\s;{}#"\'`\x00-\x1f\x7f]{1,255}$')
_SIZE_RE = re.compile(r'^\d{1,10}[kKmMgG]?$')
_BUFFERS_RE = re.compile(r'^\d{1,6} +\d{1,10}[kKmMgG]?$')
_CACHE_VALID_RE = re.compile(r'^((\d{3}|any) +)*\d{1,6}(ms|[smhdwMy])?$')
_CACHE_BYPASS_RE = re.compile(r'^\$[A-Za-z0-9_]+( +\$[A-Za-z0-9_]+)*$')
_HEADER_NAME_RE = re.compile(r'^[A-Za-z0-9-]{1,64}$')
# proxy_set_header values are emitted bare: one token, nginx variables allowed.
_BARE_HEADER_VALUE_RE = re.compile(r'^[^\s;{}#"\'`\\\x00-\x1f\x7f]{1,512}$')
# add_header values are emitted inside double quotes.
_QUOTED_HEADER_VALUE_RE = re.compile(r'^[^"\\\x00-\x1f\x7f]{0,1024}$')
_ERROR_CODE_RE = re.compile(r'^[3-5]\d\d$')
_ERROR_PAGE_RE = re.compile(r"^(/[A-Za-z0-9._~/%-]*|https?://[^\s;{}#\"'`$\\\x00-\x1f\x7f]+|@[A-Za-z0-9_]+)$")
CDN_PROVIDERS = ('none', 'cloudflare', 'imperva', 'generic')


def _check_location_path(v: str | None) -> str | None:
    if v is None:
        return v
    if not _LOCATION_PATH_RE.match(v) or v.endswith('\\'):
        raise ValueError("Location path can't contain spaces, quotes, ';', '{', '}' or '#'")
    return v


def _check_location_path_for_type(path: str | None, match_type: str | None) -> None:
    if path is not None and match_type in ('prefix', 'exact') and not path.startswith('/'):
        raise ValueError("A prefix or exact location path must start with '/'")


def _check_match_type(v: str | None) -> str | None:
    if v is not None and v not in ('prefix', 'exact', 'regex', 'regex_case_insensitive'):
        raise ValueError('Match type must be prefix, exact, regex, or regex_case_insensitive')
    return v


def _check_size(v: str | None, what: str) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if not _SIZE_RE.match(v):
        raise ValueError(f'{what} must be a number with an optional k, m or g suffix (e.g. 100m)')
    return v


def _check_buffers(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if not _BUFFERS_RE.match(v):
        raise ValueError('Proxy buffers must be "<count> <size>", e.g. "8 4k"')
    return v


def _check_cache_valid(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not _CACHE_VALID_RE.match(v):
        raise ValueError('Cache valid must be status codes (or "any") then a time, e.g. "200 302 10m"')
    return v


def _check_cache_bypass(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not _CACHE_BYPASS_RE.match(v):
        raise ValueError('Cache bypass must be nginx variables, e.g. "$http_cache_control $cookie_nocache"')
    return v


def _check_header_names(names) -> None:
    for name in names:
        if not _HEADER_NAME_RE.match(name):
            raise ValueError(f'Invalid header name: {name!r} (letters, digits and dashes only)')


def _check_custom_headers(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is None:
        return v
    _check_header_names(v)
    for name, value in v.items():
        if not _QUOTED_HEADER_VALUE_RE.match(value):
            raise ValueError(f"Header {name}: the value can't contain double quotes, backslashes or line breaks")
    return v


def _check_proxy_headers(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is None:
        return v
    _check_header_names(v)
    for name, value in v.items():
        if not _BARE_HEADER_VALUE_RE.match(value):
            raise ValueError(f"Header {name}: the value must be one word (nginx variables allowed), no quotes or ';'")
    return v


def _check_hide_headers(v: list[str] | None) -> list[str] | None:
    if v is not None:
        _check_header_names(v)
    return v


def _check_error_pages(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is None:
        return v
    for code, page in v.items():
        if not _ERROR_CODE_RE.match(str(code)):
            raise ValueError(f'Error page status must be a 3xx-5xx code, got {code!r}')
        if not _ERROR_PAGE_RE.match(page):
            raise ValueError(f'Error page for {code} must be a /path, an http(s) URL or a @named location')
    return v


def _check_cdn_provider(v: str | None) -> str | None:
    if v is not None and v not in CDN_PROVIDERS:
        raise ValueError(f'CDN provider must be one of: {", ".join(CDN_PROVIDERS)}')
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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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
        return _check_match_type(v)

    @field_validator('path')
    @classmethod
    def path_valid(cls, v: str) -> str:
        return _check_location_path(v)

    @field_validator('forward_host')
    @classmethod
    def forward_host_valid(cls, v: str) -> str:
        return normalize_upstream_host(v)

    @field_validator('cache_valid')
    @classmethod
    def cache_valid_ok(cls, v: str | None) -> str | None:
        return _check_cache_valid(v)

    @field_validator('cache_bypass')
    @classmethod
    def cache_bypass_ok(cls, v: str | None) -> str | None:
        return _check_cache_bypass(v)

    @field_validator('custom_headers')
    @classmethod
    def custom_headers_ok(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _check_custom_headers(v)

    @field_validator('proxy_headers')
    @classmethod
    def proxy_headers_ok(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _check_proxy_headers(v)

    @field_validator('hide_headers')
    @classmethod
    def hide_headers_ok(cls, v: list[str] | None) -> list[str] | None:
        return _check_hide_headers(v)

    @model_validator(mode='after')
    def path_fits_match_type(self):
        _check_location_path_for_type(self.path, self.match_type)
        return self


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

    # The same checks as create: an update reaches the config just the same.
    @field_validator('forward_port')
    @classmethod
    def port_range(cls, v: int | None) -> int | None:
        return _check_port(v)

    @field_validator('forward_scheme')
    @classmethod
    def scheme_valid(cls, v: str | None) -> str | None:
        return _check_scheme(v)

    @field_validator('match_type')
    @classmethod
    def match_type_valid(cls, v: str | None) -> str | None:
        return _check_match_type(v)

    @field_validator('path')
    @classmethod
    def path_valid(cls, v: str | None) -> str | None:
        return _check_location_path(v)

    @field_validator('forward_host')
    @classmethod
    def forward_host_valid(cls, v: str | None) -> str | None:
        return None if v is None else normalize_upstream_host(v)

    @field_validator('cache_valid')
    @classmethod
    def cache_valid_ok(cls, v: str | None) -> str | None:
        return _check_cache_valid(v)

    @field_validator('cache_bypass')
    @classmethod
    def cache_bypass_ok(cls, v: str | None) -> str | None:
        return _check_cache_bypass(v)

    @field_validator('custom_headers')
    @classmethod
    def custom_headers_ok(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _check_custom_headers(v)

    @field_validator('proxy_headers')
    @classmethod
    def proxy_headers_ok(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _check_proxy_headers(v)

    @field_validator('hide_headers')
    @classmethod
    def hide_headers_ok(cls, v: list[str] | None) -> list[str] | None:
        return _check_hide_headers(v)

    @model_validator(mode='after')
    def path_fits_match_type(self):
        _check_location_path_for_type(self.path, self.match_type)
        return self


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

    model_config = ConfigDict(from_attributes=True)


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

    @field_validator('client_max_body_size')
    @classmethod
    def body_size_ok(cls, v: str) -> str:
        return _check_size(v, 'Client max body size')

    @field_validator('proxy_buffer_size')
    @classmethod
    def buffer_size_ok(cls, v: str) -> str:
        return _check_size(v, 'Proxy buffer size')

    @field_validator('proxy_buffers')
    @classmethod
    def buffers_ok(cls, v: str) -> str:
        return _check_buffers(v)

    @field_validator('cache_valid')
    @classmethod
    def cache_valid_ok(cls, v: str | None) -> str | None:
        return _check_cache_valid(v)

    @field_validator('cache_bypass')
    @classmethod
    def cache_bypass_ok(cls, v: str | None) -> str | None:
        return _check_cache_bypass(v)

    @field_validator('custom_error_pages')
    @classmethod
    def error_pages_ok(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _check_error_pages(v)

    @field_validator('cdn_provider')
    @classmethod
    def cdn_provider_ok(cls, v: str) -> str:
        return _check_cdn_provider(v)


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

    @field_validator('client_max_body_size')
    @classmethod
    def body_size_ok(cls, v: str | None) -> str | None:
        return _check_size(v, 'Client max body size')

    @field_validator('proxy_buffer_size')
    @classmethod
    def buffer_size_ok(cls, v: str | None) -> str | None:
        return _check_size(v, 'Proxy buffer size')

    @field_validator('proxy_buffers')
    @classmethod
    def buffers_ok(cls, v: str | None) -> str | None:
        return _check_buffers(v)

    @field_validator('cache_valid')
    @classmethod
    def cache_valid_ok(cls, v: str | None) -> str | None:
        return _check_cache_valid(v)

    @field_validator('cache_bypass')
    @classmethod
    def cache_bypass_ok(cls, v: str | None) -> str | None:
        return _check_cache_bypass(v)

    @field_validator('custom_error_pages')
    @classmethod
    def error_pages_ok(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _check_error_pages(v)

    @field_validator('cdn_provider')
    @classmethod
    def cdn_provider_ok(cls, v: str | None) -> str | None:
        return _check_cdn_provider(v)

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

    model_config = ConfigDict(from_attributes=True)
