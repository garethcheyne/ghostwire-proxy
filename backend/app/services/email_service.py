"""SMTP delivery.

The email alert channel was a stub that logged and returned True — so every
"email sent" was a lie, and a scheduled report would have silently gone nowhere.
This is the real implementation.

Configuration lives in the `settings` key/value table rather than the
environment, so it can be changed from the UI without a redeploy. The password
is Fernet-encrypted at rest with the same key everything else uses.
"""
import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_data, decrypt_data
from app.models.setting import Setting

logger = logging.getLogger(__name__)

SMTP_KEYS = {
    "smtp_host": "SMTP server hostname",
    "smtp_port": "SMTP server port (587 for STARTTLS, 465 for implicit TLS)",
    "smtp_username": "SMTP username",
    "smtp_password": "SMTP password (encrypted at rest)",
    "smtp_from_address": "Address outgoing mail is sent from",
    "smtp_from_name": "Display name for outgoing mail",
    "smtp_security": "Connection security: starttls, ssl, or none",
}

# Sending is blocking socket work; it runs in a thread so it can't stall the
# event loop that is also serving the proxy's admin API.
SMTP_TIMEOUT_SECONDS = 30


class EmailNotConfigured(RuntimeError):
    """No SMTP host has been set."""


async def get_smtp_config(db: AsyncSession, include_password: bool = False) -> dict:
    """Read SMTP settings. The password is redacted unless asked for."""
    result = await db.execute(
        select(Setting).where(Setting.key.in_(list(SMTP_KEYS.keys())))
    )
    stored = {s.key: s.value for s in result.scalars().all()}

    config = {
        "host": stored.get("smtp_host") or "",
        "port": int(stored.get("smtp_port") or 587),
        "username": stored.get("smtp_username") or "",
        "from_address": stored.get("smtp_from_address") or "",
        "from_name": stored.get("smtp_from_name") or "Ghostwire Proxy",
        "security": (stored.get("smtp_security") or "starttls").lower(),
        "configured": bool(stored.get("smtp_host")),
        "has_password": bool(stored.get("smtp_password")),
    }

    if include_password:
        raw = stored.get("smtp_password")
        try:
            config["password"] = decrypt_data(raw) if raw else ""
        except Exception:
            logger.error("Stored SMTP password could not be decrypted")
            config["password"] = ""

    return config


async def save_smtp_config(db: AsyncSession, payload: dict) -> dict:
    """Persist SMTP settings. An omitted password keeps the stored one."""
    values = {
        "smtp_host": payload.get("host", "").strip(),
        "smtp_port": str(payload.get("port") or 587),
        "smtp_username": payload.get("username", "").strip(),
        "smtp_from_address": payload.get("from_address", "").strip(),
        "smtp_from_name": payload.get("from_name", "").strip() or "Ghostwire Proxy",
        "smtp_security": (payload.get("security") or "starttls").lower(),
    }

    # Only overwrite the password when a new one was actually supplied —
    # otherwise editing the host would wipe the credential.
    password = payload.get("password")
    if password:
        values["smtp_password"] = encrypt_data(password)

    existing = {
        s.key: s
        for s in (await db.execute(
            select(Setting).where(Setting.key.in_(list(values.keys())))
        )).scalars().all()
    }

    for key, value in values.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(Setting(key=key, value=value, description=SMTP_KEYS.get(key)))

    await db.commit()
    return await get_smtp_config(db)


def _send_sync(config: dict, message: EmailMessage) -> None:
    """Blocking SMTP send. Called in a worker thread."""
    host = config["host"]
    port = config["port"]
    security = config["security"]

    if security == "ssl":
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)

    try:
        server.ehlo()
        if security == "starttls":
            server.starttls(context=ssl.create_default_context())
            server.ehlo()

        if config.get("username"):
            server.login(config["username"], config.get("password", ""))

        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:
            server.close()


async def send_email(
    db: AsyncSession,
    to: list[str],
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> None:
    """Send one message. Raises on failure so callers can report it honestly."""
    config = await get_smtp_config(db, include_password=True)

    if not config["configured"]:
        raise EmailNotConfigured(
            "No SMTP server is configured. Set one up under Settings before sending mail."
        )

    recipients = [address.strip() for address in to if address and address.strip()]
    if not recipients:
        raise ValueError("No recipients specified")

    from_address = config["from_address"] or config["username"]
    if not from_address:
        raise EmailNotConfigured("No from address is configured for outgoing mail.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((config["from_name"], from_address))
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message.set_content(text_body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    await asyncio.to_thread(_send_sync, config, message)
    logger.info("Sent email %r to %d recipient(s)", subject, len(recipients))


async def send_test_email(db: AsyncSession, to: str) -> None:
    await send_email(
        db,
        to=[to],
        subject="Ghostwire Proxy — SMTP test",
        text_body=(
            "This is a test message from Ghostwire Proxy.\n\n"
            "If you are reading it, outgoing mail is configured correctly and "
            "scheduled reports and email alerts will be delivered."
        ),
        html_body=(
            "<p>This is a test message from <strong>Ghostwire Proxy</strong>.</p>"
            "<p>If you are reading it, outgoing mail is configured correctly and "
            "scheduled reports and email alerts will be delivered.</p>"
        ),
    )
