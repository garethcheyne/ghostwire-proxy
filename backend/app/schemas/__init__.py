# Import all schemas
from app.schemas.user import (
    UserBase, UserCreate, UserUpdate, UserResponse, UserCreateResponse
)
from app.schemas.auth import (
    LoginRequest, TokenResponse, RefreshRequest
)
from app.schemas.proxy_host import (
    ProxyHostBase, ProxyHostCreate, ProxyHostUpdate, ProxyHostResponse,
    UpstreamServerCreate, UpstreamServerResponse
)
from app.schemas.certificate import (
    CertificateBase, CertificateCreate, CertificateUpload, CertificateLetsEncrypt,
    CertificateResponse
)
from app.schemas.access_list import (
    AccessListBase, AccessListCreate, AccessListUpdate, AccessListResponse,
    AccessListEntryCreate, AccessListEntryResponse
)
from app.schemas.auth_wall import (
    AuthWallBase, AuthWallCreate, AuthWallUpdate, AuthWallResponse,
    LocalAuthUserCreate, LocalAuthUserResponse,
    AuthProviderCreate, AuthProviderResponse,
    LdapConfigCreate, LdapConfigResponse
)
from app.schemas.traffic import (
    TrafficLogResponse, TrafficStatsResponse
)
from app.schemas.setting import (
    SettingUpdate, SettingResponse
)
