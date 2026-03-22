"""
GitHub OAuth2 authentication provider.
"""
from typing import Optional
import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_data
from app.models.auth_wall import AuthProvider
from app.services.auth_providers.base import AuthProviderBase, UserInfo


class GitHubAuthProvider(AuthProviderBase):
    """GitHub OAuth2 authentication provider."""

    # GitHub OAuth endpoints
    AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USERINFO_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"
    DEFAULT_SCOPES = "read:user user:email"

    def __init__(self, provider: AuthProvider, db: AsyncSession):
        self.provider = provider
        self.db = db

    @property
    def provider_type(self) -> str:
        return "github"

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
        raise NotImplementedError("Use OAuth callback flow for GitHub auth")

    async def get_authorization_url(
        self,
        callback_url: str,
        state: str,
    ) -> str:
        """Generate GitHub OAuth authorization URL."""
        auth_url = self.provider.authorization_url or self.AUTHORIZATION_URL

        from urllib.parse import urlencode
        params = {
            "client_id": self.client_id,
            "redirect_uri": callback_url,
            "scope": self.scopes,
            "state": state,
            "allow_signup": "false",  # Only existing GitHub accounts
        }

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
                },
                headers={"Accept": "application/json"},
            )

            if token_response.status_code != 200:
                raise Exception(f"Token exchange failed: {token_response.text}")

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                error = token_data.get("error_description", "No access token in response")
                raise Exception(error)

            # Get user info
            userinfo_response = await client.get(
                userinfo_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

            if userinfo_response.status_code != 200:
                raise Exception(f"User info request failed: {userinfo_response.text}")

            userinfo = userinfo_response.json()

            # Get primary email (GitHub may not return email in user info)
            email = userinfo.get("email")
            if not email:
                emails_response = await client.get(
                    self.EMAILS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                if emails_response.status_code == 200:
                    emails = emails_response.json()
                    # Find primary verified email
                    for email_obj in emails:
                        if email_obj.get("primary") and email_obj.get("verified"):
                            email = email_obj.get("email")
                            break
                    # Fallback to any verified email
                    if not email:
                        for email_obj in emails:
                            if email_obj.get("verified"):
                                email = email_obj.get("email")
                                break

        # Map GitHub user info to our UserInfo
        return UserInfo(
            user_id=str(userinfo.get("id", "")),
            username=userinfo.get("login", ""),
            email=email,
            display_name=userinfo.get("name") or userinfo.get("login"),
            avatar_url=userinfo.get("avatar_url"),
            provider_type="github",
            raw_data=userinfo,
        )

    async def validate_user(
        self,
        user_info: UserInfo,
        auth_wall_id: str,
    ) -> bool:
        """
        Validate GitHub user.
        Requires a verified email.
        """
        # Require email
        if not user_info.email:
            return False
        return True
