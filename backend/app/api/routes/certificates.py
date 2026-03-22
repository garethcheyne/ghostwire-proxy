from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import encrypt_data, decrypt_data
from app.models.user import User
from app.models.certificate import Certificate
from app.models.audit_log import AuditLog
from app.schemas.certificate import (
    CertificateUpload, CertificateLetsEncrypt, CertificateResponse
)
from app.api.deps import get_current_user
from app.services.certificate_service import request_letsencrypt_certificate, renew_certificate
from app.services.openresty_service import generate_all_configs, write_certificate_files

router = APIRouter()


@router.get("/", response_model=list[CertificateResponse])
async def list_certificates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all certificates"""
    query = select(Certificate).order_by(Certificate.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def upload_certificate(
    cert_data: CertificateUpload,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a custom SSL certificate"""
    # TODO: Validate certificate and extract expiry date
    # For now, just store it

    cert = Certificate(
        name=cert_data.name,
        domain_names=cert_data.domain_names,
        certificate=cert_data.certificate,
        certificate_key=encrypt_data(cert_data.certificate_key),
        certificate_chain=cert_data.certificate_chain,
        is_letsencrypt=False,
        status="valid",
    )
    db.add(cert)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="certificate_uploaded",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Uploaded certificate: {cert_data.name}",
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(cert)

    return cert


async def process_letsencrypt_request(cert_id: str):
    """Background task to process Let's Encrypt certificate request"""
    import asyncio
    from app.core.database import async_session_maker

    async with async_session_maker() as db:
        success, message = await request_letsencrypt_certificate(db, cert_id)

        if success:
            # Write certificate files to disk for nginx
            result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
            cert = result.scalar_one_or_none()
            if cert and cert.certificate:
                await write_certificate_files(cert)

                # Regenerate nginx configs to use the new cert
                await generate_all_configs(db)

                # Reload nginx
                import socket
                import os
                docker_socket = "/var/run/docker.sock"
                if os.path.exists(docker_socket):
                    try:
                        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        sock.connect(docker_socket)
                        request_str = (
                            "POST /containers/ghostwire-proxy-nginx/kill?signal=HUP HTTP/1.1\r\n"
                            "Host: localhost\r\n"
                            "Content-Length: 0\r\n"
                            "\r\n"
                        )
                        sock.sendall(request_str.encode())
                        sock.recv(4096)
                        sock.close()
                    except Exception:
                        pass


@router.post("/letsencrypt", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def request_letsencrypt_cert(
    cert_data: CertificateLetsEncrypt,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request a Let's Encrypt certificate"""
    # Create certificate record in pending status
    cert = Certificate(
        name=cert_data.name,
        domain_names=cert_data.domain_names,
        is_letsencrypt=True,
        letsencrypt_email=cert_data.email,
        status="pending",
    )
    db.add(cert)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="letsencrypt_requested",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Requested Let's Encrypt certificate for: {', '.join(cert_data.domain_names)}",
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(cert)

    # Queue certificate request in background
    background_tasks.add_task(process_letsencrypt_request, cert.id)

    return cert


@router.get("/{cert_id}", response_model=CertificateResponse)
async def get_certificate(
    cert_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get certificate by ID"""
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    cert = result.scalar_one_or_none()

    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )

    return cert


@router.delete("/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate(
    cert_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete certificate"""
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    cert = result.scalar_one_or_none()

    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="certificate_deleted",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted certificate: {cert.name}",
    )
    db.add(audit_log)

    await db.delete(cert)
    await db.commit()


async def process_certificate_renewal(cert_id: str):
    """Background task to process certificate renewal"""
    from app.core.database import async_session_maker
    import socket
    import os

    async with async_session_maker() as db:
        success, message = await renew_certificate(db, cert_id)

        if success:
            # Write certificate files to disk for nginx
            result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
            cert = result.scalar_one_or_none()
            if cert and cert.certificate:
                await write_certificate_files(cert)
                await generate_all_configs(db)

                # Reload nginx
                docker_socket = "/var/run/docker.sock"
                if os.path.exists(docker_socket):
                    try:
                        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        sock.connect(docker_socket)
                        request_str = (
                            "POST /containers/ghostwire-proxy-nginx/kill?signal=HUP HTTP/1.1\r\n"
                            "Host: localhost\r\n"
                            "Content-Length: 0\r\n"
                            "\r\n"
                        )
                        sock.sendall(request_str.encode())
                        sock.recv(4096)
                        sock.close()
                    except Exception:
                        pass


@router.post("/{cert_id}/renew", response_model=CertificateResponse)
async def renew_cert(
    cert_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Renew Let's Encrypt certificate"""
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    cert = result.scalar_one_or_none()

    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )

    if not cert.is_letsencrypt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Let's Encrypt certificates can be renewed",
        )

    # Mark as pending renewal
    cert.status = "pending"

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="certificate_renewal_requested",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Requested certificate renewal: {cert.name}",
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(cert)

    # Queue renewal in background
    background_tasks.add_task(process_certificate_renewal, cert.id)

    return cert
