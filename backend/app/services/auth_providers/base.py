"""
Base class for auth providers.
All auth providers must implement this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserInfo:
    """Standardized user info returned by all providers."""
    user_id: str  # Unique identifier from provider
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider_type: str = ""
    raw_data: Optional[dict] = None  # Original provider response


class AuthProviderBase(ABC):
    """Abstract base class for authentication providers."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        pass

    @abstractmethod
    async def authenticate(self, credentials: dict) -> Optional[UserInfo]:
        """
        Authenticate user with provided credentials.

        For local auth: {"username": str, "password": str}
        For OAuth: Not applicable (use callback flow)
        For LDAP: {"username": str, "password": str}

        Returns UserInfo if authentication succeeds, None otherwise.
        """
        pass

    @abstractmethod
    async def get_authorization_url(
        self,
        callback_url: str,
        state: str,
    ) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            callback_url: URL to redirect after authorization
            state: CSRF protection state parameter

        Returns:
            Authorization URL to redirect user to
        """
        pass

    @abstractmethod
    async def handle_callback(
        self,
        code: str,
        state: str,
        callback_url: str,
    ) -> UserInfo:
        """
        Handle OAuth callback and exchange code for user info.

        Args:
            code: Authorization code from provider
            state: State parameter for CSRF validation
            callback_url: The callback URL used in the request

        Returns:
            UserInfo with authenticated user details

        Raises:
            Exception if callback handling fails
        """
        pass

    async def validate_user(
        self,
        user_info: UserInfo,
        auth_wall_id: str,
    ) -> bool:
        """
        Optional: Validate if user is allowed to access this auth wall.
        Override to implement custom access control (e.g., domain restrictions).

        Default implementation allows all authenticated users.
        """
        return True
