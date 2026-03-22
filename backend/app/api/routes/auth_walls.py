from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_password_hash, encrypt_data
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.auth_wall import AuthWall, LocalAuthUser, AuthProvider, LdapConfig
from app.models.audit_log import AuditLog
from app.schemas.auth_wall import (
    AuthWallCreate, AuthWallUpdate, AuthWallResponse,
    LocalAuthUserCreate, LocalAuthUserUpdate, LocalAuthUserResponse,
    AuthProviderCreate, AuthProviderUpdate, AuthProviderResponse,
    LdapConfigCreate, LdapConfigUpdate, LdapConfigResponse
)
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/", response_model=list[AuthWallResponse])
async def list_auth_walls(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all auth walls"""
    query = (
        select(AuthWall)
        .options(
            selectinload(AuthWall.local_users),
            selectinload(AuthWall.auth_providers),
            selectinload(AuthWall.ldap_configs),
        )
        .order_by(AuthWall.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=AuthWallResponse, status_code=status.HTTP_201_CREATED)
async def create_auth_wall(
    wall_data: AuthWallCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new auth wall"""
    auth_wall = AuthWall(
        name=wall_data.name,
        auth_type=wall_data.auth_type,
        session_timeout=wall_data.session_timeout,
        default_provider_id=wall_data.default_provider_id,
    )
    db.add(auth_wall)
    await db.flush()

    # Add local users if provided
    if wall_data.local_users:
        for user_data in wall_data.local_users:
            local_user = LocalAuthUser(
                auth_wall_id=auth_wall.id,
                username=user_data.username,
                password_hash=get_password_hash(user_data.password),
                display_name=user_data.display_name,
                email=user_data.email,
            )
            db.add(local_user)

    # Add auth providers if provided
    if wall_data.auth_providers:
        for provider_data in wall_data.auth_providers:
            provider = AuthProvider(
                auth_wall_id=auth_wall.id,
                name=provider_data.name,
                provider_type=provider_data.provider_type,
                client_id=provider_data.client_id,
                client_secret=encrypt_data(provider_data.client_secret),
                authorization_url=provider_data.authorization_url,
                token_url=provider_data.token_url,
                userinfo_url=provider_data.userinfo_url,
                scopes=provider_data.scopes,
                enabled=provider_data.enabled,
            )
            db.add(provider)

    # Add LDAP configs if provided
    if wall_data.ldap_configs:
        for ldap_data in wall_data.ldap_configs:
            ldap_config = LdapConfig(
                auth_wall_id=auth_wall.id,
                name=ldap_data.name,
                host=ldap_data.host,
                port=ldap_data.port,
                use_ssl=ldap_data.use_ssl,
                use_starttls=ldap_data.use_starttls,
                bind_dn=ldap_data.bind_dn,
                bind_password=encrypt_data(ldap_data.bind_password) if ldap_data.bind_password else None,
                base_dn=ldap_data.base_dn,
                user_filter=ldap_data.user_filter,
                username_attribute=ldap_data.username_attribute,
                email_attribute=ldap_data.email_attribute,
                display_name_attribute=ldap_data.display_name_attribute,
                enabled=ldap_data.enabled,
            )
            db.add(ldap_config)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="auth_wall_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created auth wall: {wall_data.name}",
    )
    db.add(audit_log)
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(AuthWall)
        .options(
            selectinload(AuthWall.local_users),
            selectinload(AuthWall.auth_providers),
            selectinload(AuthWall.ldap_configs),
        )
        .where(AuthWall.id == auth_wall.id)
    )
    return result.scalar_one()


@router.get("/{wall_id}", response_model=AuthWallResponse)
async def get_auth_wall(
    wall_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get auth wall by ID"""
    result = await db.execute(
        select(AuthWall)
        .options(
            selectinload(AuthWall.local_users),
            selectinload(AuthWall.auth_providers),
            selectinload(AuthWall.ldap_configs),
        )
        .where(AuthWall.id == wall_id)
    )
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    return auth_wall


@router.put("/{wall_id}", response_model=AuthWallResponse)
async def update_auth_wall(
    wall_id: str,
    wall_data: AuthWallUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update auth wall"""
    result = await db.execute(
        select(AuthWall)
        .options(
            selectinload(AuthWall.local_users),
            selectinload(AuthWall.auth_providers),
            selectinload(AuthWall.ldap_configs),
        )
        .where(AuthWall.id == wall_id)
    )
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    for field, value in wall_data.model_dump(exclude_unset=True).items():
        setattr(auth_wall, field, value)

    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="auth_wall_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated auth wall: {auth_wall.name}",
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(auth_wall)

    return auth_wall


@router.delete("/{wall_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_auth_wall(
    wall_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete auth wall"""
    result = await db.execute(select(AuthWall).where(AuthWall.id == wall_id))
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="auth_wall_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted auth wall: {auth_wall.name}",
    )
    db.add(audit_log)

    await db.delete(auth_wall)
    await db.commit()


# Local users management
@router.post("/{wall_id}/users", response_model=LocalAuthUserResponse, status_code=status.HTTP_201_CREATED)
async def add_local_user(
    wall_id: str,
    user_data: LocalAuthUserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add local user to auth wall"""
    result = await db.execute(select(AuthWall).where(AuthWall.id == wall_id))
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    local_user = LocalAuthUser(
        auth_wall_id=wall_id,
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        display_name=user_data.display_name,
        email=user_data.email,
    )
    db.add(local_user)
    await db.commit()
    await db.refresh(local_user)

    return local_user


@router.delete("/{wall_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_local_user(
    wall_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove local user from auth wall"""
    result = await db.execute(
        select(LocalAuthUser).where(
            (LocalAuthUser.id == user_id) &
            (LocalAuthUser.auth_wall_id == wall_id)
        )
    )
    local_user = result.scalar_one_or_none()

    if not local_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.delete(local_user)
    await db.commit()


# Auth providers management
@router.post("/{wall_id}/providers", response_model=AuthProviderResponse, status_code=status.HTTP_201_CREATED)
async def add_auth_provider(
    wall_id: str,
    provider_data: AuthProviderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add OAuth provider to auth wall"""
    result = await db.execute(select(AuthWall).where(AuthWall.id == wall_id))
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    provider = AuthProvider(
        auth_wall_id=wall_id,
        name=provider_data.name,
        provider_type=provider_data.provider_type,
        client_id=provider_data.client_id,
        client_secret=encrypt_data(provider_data.client_secret),
        authorization_url=provider_data.authorization_url,
        token_url=provider_data.token_url,
        userinfo_url=provider_data.userinfo_url,
        scopes=provider_data.scopes,
        enabled=provider_data.enabled,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    return provider


@router.delete("/{wall_id}/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_auth_provider(
    wall_id: str,
    provider_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove OAuth provider from auth wall"""
    result = await db.execute(
        select(AuthProvider).where(
            (AuthProvider.id == provider_id) &
            (AuthProvider.auth_wall_id == wall_id)
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    await db.delete(provider)
    await db.commit()


# LDAP configs management
@router.post("/{wall_id}/ldap", response_model=LdapConfigResponse, status_code=status.HTTP_201_CREATED)
async def add_ldap_config(
    wall_id: str,
    ldap_data: LdapConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add LDAP config to auth wall"""
    result = await db.execute(select(AuthWall).where(AuthWall.id == wall_id))
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    ldap_config = LdapConfig(
        auth_wall_id=wall_id,
        name=ldap_data.name,
        host=ldap_data.host,
        port=ldap_data.port,
        use_ssl=ldap_data.use_ssl,
        use_starttls=ldap_data.use_starttls,
        bind_dn=ldap_data.bind_dn,
        bind_password=encrypt_data(ldap_data.bind_password) if ldap_data.bind_password else None,
        base_dn=ldap_data.base_dn,
        user_filter=ldap_data.user_filter,
        username_attribute=ldap_data.username_attribute,
        email_attribute=ldap_data.email_attribute,
        display_name_attribute=ldap_data.display_name_attribute,
        enabled=ldap_data.enabled,
    )
    db.add(ldap_config)
    await db.commit()
    await db.refresh(ldap_config)

    return ldap_config


@router.delete("/{wall_id}/ldap/{ldap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_ldap_config(
    wall_id: str,
    ldap_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove LDAP config from auth wall"""
    result = await db.execute(
        select(LdapConfig).where(
            (LdapConfig.id == ldap_id) &
            (LdapConfig.auth_wall_id == wall_id)
        )
    )
    ldap_config = result.scalar_one_or_none()

    if not ldap_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LDAP config not found",
        )

    await db.delete(ldap_config)
    await db.commit()
