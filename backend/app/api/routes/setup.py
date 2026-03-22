"""
First-run setup routes.
These routes are only accessible when no users exist in the database.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.security import get_password_hash, create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.auth import TokenResponse

router = APIRouter()


class SetupCheckResponse(BaseModel):
    setup_required: bool
    message: str


class SetupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


async def check_setup_required(db: AsyncSession) -> bool:
    """Check if setup is required (no users exist)"""
    result = await db.execute(select(func.count(User.id)))
    count = result.scalar() or 0
    return count == 0


@router.get("/check", response_model=SetupCheckResponse)
async def check_setup(
    db: AsyncSession = Depends(get_db),
):
    """Check if initial setup is required"""
    setup_required = await check_setup_required(db)

    if setup_required:
        return SetupCheckResponse(
            setup_required=True,
            message="No users found. Please complete initial setup.",
        )

    return SetupCheckResponse(
        setup_required=False,
        message="System is already configured.",
    )


@router.post("/initialize", response_model=TokenResponse)
async def initialize_system(
    setup_data: SetupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize the system with the first admin user.
    This endpoint is only accessible when no users exist.
    """
    # Check if setup is still required
    setup_required = await check_setup_required(db)

    if not setup_required:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already initialized",
        )

    # Validate password strength
    if len(setup_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    # Create the admin user
    user = User(
        email=setup_data.email.lower(),
        name=setup_data.name,
        password_hash=get_password_hash(setup_data.password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create tokens and log them in
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )
