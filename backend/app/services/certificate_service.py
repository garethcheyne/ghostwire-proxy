"""
Certificate management service.
Handles Let's Encrypt certificate requests and renewals.
"""
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import encrypt_data
from app.models.certificate import Certificate


def _parse_certificate_expiry(certificate_pem: str) -> datetime:
    """Read the real notAfter date out of a PEM certificate.

    Used instead of assuming "Let's Encrypt = 90 days from now", which is
    wrong whenever `certbot renew` is a no-op (cert wasn't actually due yet,
    so the current on-disk cert - possibly issued weeks ago - gets re-read
    unchanged) but the caller still stamps a fresh 90-day expiry on it.
    """
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(certificate_pem.encode())
    return cert.not_valid_after_utc


async def request_letsencrypt_certificate(
    db: AsyncSession,
    cert_id: str,
) -> tuple[bool, str]:
    """
    Request a Let's Encrypt certificate using certbot.

    This should be called from a background task/worker.
    """
    # Get certificate record
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    cert = result.scalar_one_or_none()

    if not cert:
        return False, "Certificate not found"

    if not cert.is_letsencrypt:
        return False, "Not a Let's Encrypt certificate"

    try:
        # Build certbot command
        domains = cert.domain_names
        domain_args = []
        for domain in domains:
            domain_args.extend(["-d", domain])

        cmd = [
            "certbot", "certonly",
            "--webroot",
            "-w", "/var/www/certbot",
            "--email", cert.letsencrypt_email,
            "--agree-tos",
            "--non-interactive",
            *domain_args,
        ]

        # Add staging flag if configured
        if settings.letsencrypt_staging:
            cmd.append("--staging")

        # Run certbot
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )

        if result.returncode != 0:
            cert.status = "error"
            cert.error_message = result.stderr
            await db.commit()
            return False, result.stderr

        # Read generated certificate
        domain = domains[0]
        cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        key_path = f"/etc/letsencrypt/live/{domain}/privkey.pem"

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            cert.status = "error"
            cert.error_message = "Certificate files not found after certbot"
            await db.commit()
            return False, "Certificate files not found"

        with open(cert_path, "r") as f:
            certificate_content = f.read()

        with open(key_path, "r") as f:
            key_content = f.read()

        # Update certificate record
        cert.certificate = certificate_content
        cert.certificate_key = encrypt_data(key_content)
        cert.status = "valid"
        cert.error_message = None
        cert.last_renewed_at = datetime.now(timezone.utc)

        cert.expires_at = _parse_certificate_expiry(certificate_content)

        await db.commit()

        return True, "Certificate obtained successfully"

    except subprocess.TimeoutExpired:
        cert.status = "error"
        cert.error_message = "Certbot timed out"
        await db.commit()
        return False, "Certbot timed out"

    except Exception as e:
        cert.status = "error"
        cert.error_message = str(e)
        await db.commit()
        return False, str(e)


async def renew_certificate(
    db: AsyncSession,
    cert_id: str,
) -> tuple[bool, str]:
    """
    Renew a Let's Encrypt certificate.
    """
    # Get certificate record
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    cert = result.scalar_one_or_none()

    if not cert:
        return False, "Certificate not found"

    if not cert.is_letsencrypt:
        return False, "Not a Let's Encrypt certificate"

    domain = cert.domain_names[0]

    # Never issued (the first request failed): certbot has nothing to renew and would only say
    # "No certificate found", hiding the real cause. Request it instead.
    if not os.path.exists(f"/etc/letsencrypt/renewal/{domain}.conf"):
        return await request_letsencrypt_certificate(db, cert_id)

    try:
        # Run certbot renew
        cmd = [
            "certbot", "renew",
            "--cert-name", domain,
            "--non-interactive",
        ]

        if settings.letsencrypt_staging:
            cmd.append("--staging")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            cert.status = "error"
            cert.error_message = result.stderr
            await db.commit()
            return False, result.stderr

        # Re-read certificate
        cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        key_path = f"/etc/letsencrypt/live/{domain}/privkey.pem"

        with open(cert_path, "r") as f:
            certificate_content = f.read()

        with open(key_path, "r") as f:
            key_content = f.read()

        # Update certificate record
        cert.certificate = certificate_content
        cert.certificate_key = encrypt_data(key_content)
        cert.status = "valid"
        cert.error_message = None
        cert.last_renewed_at = datetime.now(timezone.utc)
        cert.expires_at = _parse_certificate_expiry(certificate_content)

        await db.commit()

        return True, "Certificate renewed successfully"

    except Exception as e:
        cert.status = "error"
        cert.error_message = str(e)
        await db.commit()
        return False, str(e)


async def renew_and_deploy_certificate(cert_id: str) -> tuple[bool, str]:
    """
    Renew a Let's Encrypt certificate and, on success, deploy it: write the
    renewed cert/key to the on-disk certificate store nginx reads from,
    regenerate the nginx vhost configs, and reload nginx.

    This is the single place that should be used to renew a certificate —
    both the manual "Renew" button and the automatic renewal loop in
    main.py call this, so the deploy step (which was previously only ever
    triggered from the API route as a one-off background task) always runs.
    Opens its own DB session so it's safe to call from a background task or
    a scheduler loop that doesn't already have one.
    """
    from app.core.database import async_session_maker
    from app.services.openresty_service import generate_all_configs, write_certificate_files, reload_nginx

    async with async_session_maker() as db:
        success, message = await renew_certificate(db, cert_id)

        if success:
            result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
            cert = result.scalar_one_or_none()
            if cert and cert.certificate:
                await write_certificate_files(cert)
                await generate_all_configs(db)
                reload_nginx()

        return success, message


async def check_expiring_certificates(
    db: AsyncSession,
    days_before_expiry: int = 30,
    send_notifications: bool = True,
) -> list[Certificate]:
    """
    Find certificates expiring within the specified number of days.
    Optionally sends push notifications for expiring certificates.
    """
    from datetime import timedelta

    expiry_threshold = datetime.now(timezone.utc) + timedelta(days=days_before_expiry)

    result = await db.execute(
        select(Certificate).where(
            (Certificate.expires_at != None) &
            (Certificate.expires_at <= expiry_threshold) &
            (Certificate.auto_renew == True) &
            (Certificate.is_letsencrypt == True)
        )
    )

    expiring_certs = list(result.scalars().all())

    # Send push notifications for expiring certificates
    if send_notifications and expiring_certs:
        try:
            from app.services.push_service import push_service

            for cert in expiring_certs:
                days_left = (cert.expires_at - datetime.now(timezone.utc)).days
                if days_left <= 7:  # Only notify for certs expiring within 7 days
                    domain = cert.domain_names[0] if cert.domain_names else "Unknown"
                    await push_service.notify_certificate_expiring(
                        domain=domain,
                        days=days_left,
                        db=db,
                    )
        except Exception:
            pass  # Don't fail certificate check if notifications fail

    return expiring_certs


def validate_certificate_pem(certificate_pem: str, key_pem: str) -> tuple[bool, Optional[str], Optional[datetime]]:
    """
    Validate a certificate and key pair.
    Returns (is_valid, error_message, expiry_date)
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        # Parse certificate
        cert = x509.load_pem_x509_certificate(certificate_pem.encode())

        # Parse key
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)

        # Check if key matches certificate
        cert_public_key = cert.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        key_public_key = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        if cert_public_key != key_public_key:
            return False, "Certificate and key do not match", None

        # Get expiry date
        expiry = cert.not_valid_after_utc

        return True, None, expiry

    except Exception as e:
        return False, str(e), None
