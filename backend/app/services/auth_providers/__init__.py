"""
Auth Providers Module
Modular authentication providers for Auth Wall.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_wall import AuthWall, AuthProvider, LocalAuthUser, LdapConfig
from app.services.auth_providers.base import AuthProviderBase, UserInfo
from app.services.auth_providers.local import LocalAuthProvider
from app.services.auth_providers.google import GoogleAuthProvider
from app.services.auth_providers.github import GitHubAuthProvider


class ProviderFactory:
    """Factory for creating auth provider instances."""

    @staticmethod
    def get_local_provider(
        auth_wall: AuthWall,
        db: AsyncSession,
    ) -> LocalAuthProvider:
        """Get local auth provider for an auth wall."""
        return LocalAuthProvider(auth_wall=auth_wall, db=db)

    @staticmethod
    def get_oauth_provider(
        provider: AuthProvider,
        db: AsyncSession,
    ) -> Optional[AuthProviderBase]:
        """Get OAuth provider by provider type."""
        if provider.provider_type == "google":
            return GoogleAuthProvider(provider=provider, db=db)
        elif provider.provider_type == "github":
            return GitHubAuthProvider(provider=provider, db=db)
        # Add more providers here as needed
        return None


__all__ = [
    "AuthProviderBase",
    "UserInfo",
    "LocalAuthProvider",
    "GoogleAuthProvider",
    "GitHubAuthProvider",
    "ProviderFactory",
]
