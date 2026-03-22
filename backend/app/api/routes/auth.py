from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest
from app.schemas.user import UserResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return JWT tokens"""
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == login_request.email.lower())
    )
    user = result.scalar_one_or_none()

    # Verify credentials
    if not user or not verify_password(login_request.password, user.password_hash):
        # Log failed attempt
        audit_log = AuditLog(
            user_id=user.id if user else None,
            email=login_request.email,
            action="login_failed",
            ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                       (request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
            details="Invalid credentials",
        )
        db.add(audit_log)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Update user login stats
    user.signin_count += 1
    user.last_signin_at = datetime.now(timezone.utc)

    # Log successful login
    audit_log = AuditLog(
        user_id=user.id,
        email=user.email,
        action="login_success",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token"""
    payload = decode_token(refresh_request.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user info"""
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout current user (audit log only, token invalidation is client-side)"""
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="logout",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()

    return {"message": "Logged out successfully"}
