"""Rate limiting configuration API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.rate_limit import RateLimitRule
from app.models.audit_log import AuditLog
from app.schemas.rate_limit import (
    RateLimitRuleCreate, RateLimitRuleUpdate, RateLimitRuleResponse,
)
from app.api.deps import get_current_user

router = APIRouter()


@router.get("", response_model=list[RateLimitRuleResponse])
async def list_rate_limits(
    proxy_host_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(RateLimitRule).order_by(RateLimitRule.name)
    if proxy_host_id:
        query = query.where(RateLimitRule.proxy_host_id == proxy_host_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=RateLimitRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rate_limit(
    data: RateLimitRuleCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule = RateLimitRule(**data.model_dump())
    db.add(rule)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="rate_limit_created",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Created rate limit rule: {data.name}",
    ))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/{rule_id}", response_model=RateLimitRuleResponse)
async def get_rate_limit(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RateLimitRule).where(RateLimitRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rate limit rule not found")
    return rule


@router.put("/{rule_id}", response_model=RateLimitRuleResponse)
async def update_rate_limit(
    rule_id: str,
    data: RateLimitRuleUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RateLimitRule).where(RateLimitRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rate limit rule not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="rate_limit_updated",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated rate limit rule: {rule.name}",
    ))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_limit(
    rule_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RateLimitRule).where(RateLimitRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rate limit rule not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="rate_limit_deleted",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted rate limit rule: {rule.name}",
    ))
    await db.delete(rule)
    await db.commit()
