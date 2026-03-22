from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    debug: bool = False
    log_level: str = "INFO"

    # Database (PostgreSQL)
    database_url: str = "postgresql+asyncpg://ghostwire:ghostwire@localhost:5432/ghostwire_proxy"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # JWT
    jwt_secret: str
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS512"

    # Encryption
    encryption_key: str

    # Bcrypt
    bcrypt_rounds: int = 12

    # CORS
    cors_origins: str = "http://localhost:88,http://localhost:3000"

    # OpenResty
    nginx_config_path: str = "/data/nginx-configs"
    certificates_path: str = "/data/certificates"

    # Auth Portal (URLs for proxying auth pages)
    auth_portal_frontend_url: str = "http://ghostwire-proxy-ui:3000"
    auth_portal_api_url: str = "http://ghostwire-proxy-api:8000"

    # Let's Encrypt
    letsencrypt_email: str = ""
    letsencrypt_staging: bool = False

    # Optional: Ghostwire sync
    ghostwire_api_url: str = ""
    ghostwire_api_key: str = ""

    # Web Push (VAPID keys)
    # Generate with: python -c "from pywebpush import webpush; print(webpush.generate_vapid_keypair())"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_email: str = "mailto:admin@ghostwire.local"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def sync_database_url(self) -> str:
        """Sync database URL for Alembic migrations."""
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "+psycopg2")
        return url

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
