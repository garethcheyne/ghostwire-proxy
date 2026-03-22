"""
Google OAuth2 authentication provider.
"""
from typing import Optional
import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_data
from app.models.auth_wall import AuthProvider
from app.services.auth_providers.base import AuthProviderBase, UserInfo


class GoogleAuthProvider(AuthProviderBase):
    """Google OAuth2 authentication provider."""

    # Google OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    DEFAULT_SCOPES = "openid email profile"

    def __init__(self, provider: AuthProvider, db: AsyncSession):
        self.provider = provider
        self.db = db

    @property
    def provider_type(self) -> str:
        return "google"

    @property
    def client_id(self) -> str:
        return self.provider.client_id or ""

    @property
    def client_secret(self) -> str:
        if self.provider.client_secret:
            try:
                return decrypt_data(self.provider.client_secret)
            except Exception:
                return self.provider.client_secret
        return ""

    @property
    def scopes(self) -> str:
        return self.provider.scopes or self.DEFAULT_SCOPES

    async def authenticate(self, credentials: dict) -> Optional[UserInfo]:
        """Not applicable for OAuth - use callback flow."""
        raise NotImplementedError("Use OAuth callback flow for Google auth")

    async def get_authorization_url(
        self,
        callback_url: str,
        state: str,
    ) -> str:
        """Generate Google OAuth authorization URL."""
        auth_url = self.provider.authorization_url or self.AUTHORIZATION_URL

        params = {
            "client_id": self.client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": self.scopes,
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "select_account",  # Always show account selector
        }

        query_string = "&".join(f"{k}={httpx.QueryParams({k: v})}" for k, v in params.items())
        # Use proper URL encoding
        from urllib.parse import urlencode
        return f"{auth_url}?{urlencode(params)}"

    async def handle_callback(
        self,
        code: str,
        state: str,
        callback_url: str,
    ) -> UserInfo:
        """Exchange authorization code for tokens and get user info."""
        token_url = self.provider.token_url or self.TOKEN_URL
        userinfo_url = self.provider.userinfo_url or self.USERINFO_URL

        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_response = await client.post(
                token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )

            if token_response.status_code != 200:
                raise Exception(f"Token exchange failed: {token_response.text}")

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                raise Exception("No access token in response")

            # Get user info
            userinfo_response = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if userinfo_response.status_code != 200:
                raise Exception(f"User info request failed: {userinfo_response.text}")

            userinfo = userinfo_response.json()

        # Map Google user info to our UserInfo
        return UserInfo(
            user_id=userinfo.get("sub", ""),
            username=userinfo.get("email", "").split("@")[0],
            email=userinfo.get("email"),
            display_name=userinfo.get("name"),
            avatar_url=userinfo.get("picture"),
            provider_type="google",
            raw_data=userinfo,
        )

    async def validate_user(
        self,
        user_info: UserInfo,
        auth_wall_id: str,
    ) -> bool:
        """
        Validate Google user.
        Can be extended to check email domain restrictions.
        """
        # Ensure email is verified
        raw_data = user_info.raw_data or {}
        if not raw_data.get("email_verified", False):
            return False
        return True
