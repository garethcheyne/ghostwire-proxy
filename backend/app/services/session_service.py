"""
Session Service for Auth Wall authentication.
Handles session creation, validation, revocation, and cookie signing.
"""
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func

from app.core.config import settings
from app.models.auth_wall import AuthWall
from app.models.auth_wall_session import AuthWallSession, generate_session_id


class SessionService:
    """Manages auth wall sessions with signed cookies."""

    COOKIE_NAME = "gw_auth_session"
    SIGNATURE_LENGTH = 32  # Characters in HMAC signature

    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_signing_key(self) -> bytes:
        """Get the key used for signing session cookies."""
        return settings.jwt_secret.encode()

    def _sign_session_id(self, session_id: str) -> str:
        """Generate HMAC-SHA256 signature for session ID."""
        signature = hmac.new(
            self._get_signing_key(),
            session_id.encode(),
            hashlib.sha256
        ).hexdigest()[:self.SIGNATURE_LENGTH]
        return signature

    def create_session_cookie(self, session_id: str) -> str:
        """Create a signed session cookie value."""
        signature = self._sign_session_id(session_id)
        return f"{session_id}.{signature}"

    def verify_session_cookie(self, cookie_value: str) -> Optional[str]:
        """Verify session cookie signature and return session_id if valid."""
        if not cookie_value or "." not in cookie_value:
            return None

        parts = cookie_value.rsplit(".", 1)
        if len(parts) != 2:
            return None

        session_id, signature = parts
        expected_signature = self._sign_session_id(session_id)

        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(signature, expected_signature):
            return session_id
        return None

    async def create_session(
        self,
        auth_wall_id: str,
        user_type: str,
        user_id: str,
        username: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[AuthWallSession, str]:
        """
        Create a new session and return the session object and signed cookie.

        Returns:
            Tuple of (session, cookie_value)
        """
        # Get auth wall for session timeout
        result = await self.db.execute(
            select(AuthWall).where(AuthWall.id == auth_wall_id)
        )
        auth_wall = result.scalar_one_or_none()
        if not auth_wall:
            raise ValueError(f"Auth wall not found: {auth_wall_id}")

        # Calculate expiry
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=auth_wall.session_timeout)

        # Create session
        session = AuthWallSession(
            id=generate_session_id(),
            auth_wall_id=auth_wall_id,
            user_type=user_type,
            user_id=user_id,
            username=username,
            email=email,
            display_name=display_name,
            provider_id=provider_id,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,  # Truncate
            created_at=now,
            expires_at=expires_at,
            last_activity_at=now,
        )

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        # Create signed cookie
        cookie_value = self.create_session_cookie(session.id)

        return session, cookie_value

    async def validate_session(
        self,
        session_id: str,
        auth_wall_id: str,
    ) -> Optional[AuthWallSession]:
        """
        Validate a session and return it if valid.

        Checks:
        - Session exists
        - Session belongs to the specified auth wall
        - Session is not revoked
        - Session has not expired
        """
        result = await self.db.execute(
            select(AuthWallSession).where(
                and_(
                    AuthWallSession.id == session_id,
                    AuthWallSession.auth_wall_id == auth_wall_id,
                    AuthWallSession.revoked == False,
                    AuthWallSession.expires_at > datetime.now(timezone.utc),
                )
            )
        )
        session = result.scalar_one_or_none()
        return session

    async def update_activity(self, session_id: str) -> bool:
        """
        Update session last_activity_at timestamp.
        Should be called periodically (debounced) to track user activity.
        """
        result = await self.db.execute(
            update(AuthWallSession)
            .where(AuthWallSession.id == session_id)
            .values(last_activity_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def revoke_session(
        self,
        session_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Revoke a specific session."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(AuthWallSession)
            .where(AuthWallSession.id == session_id)
            .values(
                revoked=True,
                revoked_at=now,
                revoked_reason=reason,
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def revoke_user_sessions(
        self,
        auth_wall_id: str,
        user_id: str,
        reason: Optional[str] = None,
        exclude_session_id: Optional[str] = None,
    ) -> int:
        """
        Revoke all sessions for a user in an auth wall.
        Optionally exclude a specific session (e.g., current session).
        """
        now = datetime.now(timezone.utc)
        query = (
            update(AuthWallSession)
            .where(
                and_(
                    AuthWallSession.auth_wall_id == auth_wall_id,
                    AuthWallSession.user_id == user_id,
                    AuthWallSession.revoked == False,
                )
            )
            .values(
                revoked=True,
                revoked_at=now,
                revoked_reason=reason or "User sessions revoked",
            )
        )

        if exclude_session_id:
            query = query.where(AuthWallSession.id != exclude_session_id)

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def revoke_all_sessions(
        self,
        auth_wall_id: str,
        reason: Optional[str] = None,
    ) -> int:
        """Revoke all sessions for an auth wall."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(AuthWallSession)
            .where(
                and_(
                    AuthWallSession.auth_wall_id == auth_wall_id,
                    AuthWallSession.revoked == False,
                )
            )
            .values(
                revoked=True,
                revoked_at=now,
                revoked_reason=reason or "All sessions revoked",
            )
        )
        await self.db.commit()
        return result.rowcount

    async def list_sessions(
        self,
        auth_wall_id: str,
        user_id: Optional[str] = None,
        include_revoked: bool = False,
        include_expired: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AuthWallSession], int]:
        """
        List sessions for an auth wall with pagination.

        Returns:
            Tuple of (sessions, total_count)
        """
        # Base query
        conditions = [AuthWallSession.auth_wall_id == auth_wall_id]

        if user_id:
            conditions.append(AuthWallSession.user_id == user_id)
        if not include_revoked:
            conditions.append(AuthWallSession.revoked == False)
        if not include_expired:
            conditions.append(AuthWallSession.expires_at > datetime.now(timezone.utc))

        # Count total
        count_query = select(func.count()).select_from(AuthWallSession).where(and_(*conditions))
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Get sessions
        query = (
            select(AuthWallSession)
            .where(and_(*conditions))
            .order_by(AuthWallSession.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self.db.execute(query)
        sessions = list(result.scalars().all())

        return sessions, total

    async def cleanup_expired_sessions(self, older_than_days: int = 7) -> int:
        """
        Delete expired sessions older than the specified number of days.
        This is a maintenance task to prevent database bloat.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        result = await self.db.execute(
            delete(AuthWallSession).where(
                and_(
                    AuthWallSession.expires_at < cutoff,
                )
            )
        )
        await self.db.commit()
        return result.rowcount

    async def get_active_session_count(self, auth_wall_id: str) -> int:
        """Get count of active (non-revoked, non-expired) sessions."""
        result = await self.db.execute(
            select(func.count())
            .select_from(AuthWallSession)
            .where(
                and_(
                    AuthWallSession.auth_wall_id == auth_wall_id,
                    AuthWallSession.revoked == False,
                    AuthWallSession.expires_at > datetime.now(timezone.utc),
                )
            )
        )
        return result.scalar() or 0


def get_cookie_header(
    cookie_value: str,
    session_timeout: int,
    secure: bool = True,
    domain: str = None,
) -> str:
    """
    Generate Set-Cookie header value for session cookie.

    Args:
        cookie_value: The signed cookie value
        session_timeout: Session timeout in seconds
        secure: Whether to set the Secure flag (should be True in production)
        domain: Optional domain for the cookie
    """
    parts = [
        f"{SessionService.COOKIE_NAME}={cookie_value}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={session_timeout}",
    ]
    if domain:
        parts.append(f"Domain={domain}")
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def get_clear_cookie_header() -> str:
    """Generate Set-Cookie header to clear the session cookie."""
    return f"{SessionService.COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0"
