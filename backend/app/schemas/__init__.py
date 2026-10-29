# Import all schemas
from app.schemas.access_list import (
    AccessListBase,
    AccessListCreate,
    AccessListEntryCreate,
    AccessListEntryResponse,
    AccessListResponse,
    AccessListUpdate,
)
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.auth_wall import (
    AuthProviderCreate,
    AuthProviderResponse,
    AuthWallBase,
    AuthWallCreate,
    AuthWallResponse,
    AuthWallUpdate,
    LdapConfigCreate,
    LdapConfigResponse,
    LocalAuthUserCreate,
    LocalAuthUserResponse,
)
from app.schemas.certificate import (
    CertificateBase,
    CertificateCreate,
    CertificateLetsEncrypt,
    CertificateResponse,
    CertificateUpload,
)
from app.schemas.proxy_host import (
    ProxyHostBase,
    ProxyHostCreate,
    ProxyHostResponse,
    ProxyHostUpdate,
    UpstreamServerCreate,
    UpstreamServerResponse,
)
from app.schemas.setting import SettingResponse, SettingUpdate
from app.schemas.traffic import TrafficLogResponse, TrafficStatsResponse
from app.schemas.user import UserBase, UserCreate, UserCreateResponse, UserResponse, UserUpdate
