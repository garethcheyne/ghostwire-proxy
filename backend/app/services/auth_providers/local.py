"""
Local authentication provider with TOTP support.
"""
import secrets
import json
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.security import verify_password, encrypt_data, decrypt_data
from app.models.auth_wall import AuthWall, LocalAuthUser
from app.services.auth_providers.base import AuthProviderBase, UserInfo

# TOTP support
try:
    import pyotp
    TOTP_AVAILABLE = True
except ImportError:
    TOTP_AVAILABLE = False


class LocalAuthProvider(AuthProviderBase):
    """Local username/password authentication with TOTP support."""

    # Security settings
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    BACKUP_CODE_COUNT = 10
    BACKUP_CODE_LENGTH = 8

    def __init__(self, auth_wall: AuthWall, db: AsyncSession):
        self.auth_wall = auth_wall
        self.db = db

    @property
    def provider_type(self) -> str:
        return "local"

    async def authenticate(self, credentials: dict) -> Optional[UserInfo]:
        """
        Authenticate with username and password.

        credentials:
            username: str
            password: str
        """
        username = credentials.get("username", "").strip()
        password = credentials.get("password", "")

        if not username or not password:
            return None

        # Find user
        result = await self.db.execute(
            select(LocalAuthUser).where(
                LocalAuthUser.auth_wall_id == self.auth_wall.id,
                LocalAuthUser.username == username,
                LocalAuthUser.is_active == True,
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Check if account is locked
        if user.is_locked():
            return None

        # Verify password
        if not verify_password(password, user.password_hash):
            await self._record_failed_attempt(user)
            return None

        # Password correct - reset failed attempts
        await self._reset_failed_attempts(user)

        return UserInfo(
            user_id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            provider_type="local",
        )

    async def _record_failed_attempt(self, user: LocalAuthUser) -> None:
        """Record a failed login attempt."""
        now = datetime.now(timezone.utc)
        new_attempts = user.failed_attempts + 1

        update_values = {
            "failed_attempts": new_attempts,
            "last_failed_at": now,
        }

        # Lock account if max attempts exceeded
        if new_attempts >= self.MAX_FAILED_ATTEMPTS:
            update_values["locked_until"] = now + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)

        await self.db.execute(
            update(LocalAuthUser)
            .where(LocalAuthUser.id == user.id)
            .values(**update_values)
        )
        await self.db.commit()

    async def _reset_failed_attempts(self, user: LocalAuthUser) -> None:
        """Reset failed attempts after successful login."""
        if user.failed_attempts > 0 or user.locked_until:
            await self.db.execute(
                update(LocalAuthUser)
                .where(LocalAuthUser.id == user.id)
                .values(
                    failed_attempts=0,
                    locked_until=None,
                    last_failed_at=None,
                )
            )
            await self.db.commit()

    def requires_totp(self, user: LocalAuthUser) -> bool:
        """Check if user requires TOTP verification."""
        return user.totp_enabled and user.totp_verified

    async def verify_totp(self, user: LocalAuthUser, code: str) -> bool:
        """
        Verify TOTP code.

        Args:
            user: The user to verify
            code: 6-digit TOTP code or 8-character backup code
        """
        if not TOTP_AVAILABLE:
            raise RuntimeError("TOTP support not available. Install pyotp.")

        if not user.totp_enabled or not user.totp_secret:
            return False

        # Try TOTP first
        try:
            secret = decrypt_data(user.totp_secret)
            totp = pyotp.TOTP(secret)
            if totp.verify(code, valid_window=1):
                return True
        except Exception:
            pass

        # Try backup code
        if len(code) == self.BACKUP_CODE_LENGTH:
            return await self._verify_backup_code(user, code)

        return False

    async def _verify_backup_code(self, user: LocalAuthUser, code: str) -> bool:
        """Verify and consume a backup code."""
        if not user.totp_backup_codes:
            return False

        try:
            backup_codes = json.loads(decrypt_data(user.totp_backup_codes))
        except Exception:
            return False

        code_upper = code.upper()
        if code_upper not in backup_codes:
            return False

        # Remove used backup code
        backup_codes.remove(code_upper)
        encrypted_codes = encrypt_data(json.dumps(backup_codes))

        await self.db.execute(
            update(LocalAuthUser)
            .where(LocalAuthUser.id == user.id)
            .values(totp_backup_codes=encrypted_codes)
        )
        await self.db.commit()

        return True

    async def setup_totp(self, user: LocalAuthUser) -> dict:
        """
        Initialize TOTP setup for a user.

        Returns:
            {
                "secret": str (base32 encoded),
                "provisioning_uri": str (for QR code),
                "backup_codes": list[str]
            }
        """
        if not TOTP_AVAILABLE:
            raise RuntimeError("TOTP support not available. Install pyotp.")

        # Generate new secret
        secret = pyotp.random_base32()

        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.username,
            issuer_name=f"Ghostwire Proxy - {self.auth_wall.name}",
        )

        # Generate backup codes
        backup_codes = [
            secrets.token_hex(self.BACKUP_CODE_LENGTH // 2).upper()
            for _ in range(self.BACKUP_CODE_COUNT)
        ]

        # Store encrypted secret and backup codes (not yet verified)
        await self.db.execute(
            update(LocalAuthUser)
            .where(LocalAuthUser.id == user.id)
            .values(
                totp_secret=encrypt_data(secret),
                totp_backup_codes=encrypt_data(json.dumps(backup_codes)),
                totp_enabled=False,  # Not enabled until verified
                totp_verified=False,
            )
        )
        await self.db.commit()

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "backup_codes": backup_codes,
        }

    async def verify_totp_setup(self, user: LocalAuthUser, code: str) -> bool:
        """
        Verify TOTP code during setup to enable TOTP.

        Args:
            user: The user setting up TOTP
            code: 6-digit code from authenticator app

        Returns:
            True if verification successful and TOTP enabled
        """
        if not TOTP_AVAILABLE:
            raise RuntimeError("TOTP support not available. Install pyotp.")

        if not user.totp_secret:
            return False

        try:
            secret = decrypt_data(user.totp_secret)
            totp = pyotp.TOTP(secret)
            if totp.verify(code, valid_window=1):
                # Enable TOTP
                await self.db.execute(
                    update(LocalAuthUser)
                    .where(LocalAuthUser.id == user.id)
                    .values(
                        totp_enabled=True,
                        totp_verified=True,
                    )
                )
                await self.db.commit()
                return True
        except Exception:
            pass

        return False

    async def disable_totp(self, user: LocalAuthUser) -> None:
        """Disable TOTP for a user."""
        await self.db.execute(
            update(LocalAuthUser)
            .where(LocalAuthUser.id == user.id)
            .values(
                totp_enabled=False,
                totp_verified=False,
                totp_secret=None,
                totp_backup_codes=None,
            )
        )
        await self.db.commit()

    # OAuth methods not applicable for local auth
    async def get_authorization_url(self, callback_url: str, state: str) -> str:
        raise NotImplementedError("Local auth does not use OAuth")

    async def handle_callback(self, code: str, state: str, callback_url: str) -> UserInfo:
        raise NotImplementedError("Local auth does not use OAuth")
