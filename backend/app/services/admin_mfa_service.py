"""TOTP two-factor auth for admin portal users.

The auth wall has had TOTP for visitors since the beginning
(`auth_providers/local.py`); this is the same mechanism for the `users` table —
the accounts that can rewrite proxy hosts, read traffic logs and restore
backups. The logic is deliberately a close mirror of the auth-wall provider so
the two behave identically, rather than a second dialect of the same feature.

Secrets and backup codes are Fernet-encrypted at rest via `core.security`.
"""
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_data, decrypt_data
from app.models.user import User
from app.models.setting import Setting

try:
    import pyotp
    TOTP_AVAILABLE = True
except ImportError:  # pragma: no cover - pyotp is a hard requirement in prod
    TOTP_AVAILABLE = False

# Setting key for the org-wide requirement. Stored in the same key/value
# `settings` table everything else uses.
REQUIRE_MFA_SETTING = "require_admin_mfa"

BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8
ISSUER = "Ghostwire Proxy"


class MfaNotAvailable(RuntimeError):
    """pyotp is missing from the image."""


def _require_pyotp() -> None:
    if not TOTP_AVAILABLE:
        raise MfaNotAvailable("TOTP support not available. Install pyotp.")


def generate_backup_codes() -> list[str]:
    """Ten single-use codes, shown once and stored encrypted."""
    return [
        secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()
        for _ in range(BACKUP_CODE_COUNT)
    ]


async def is_mfa_required(db: AsyncSession) -> bool:
    """Whether every admin account must have MFA enrolled."""
    result = await db.execute(
        select(Setting).where(Setting.key == REQUIRE_MFA_SETTING)
    )
    setting = result.scalar_one_or_none()
    if not setting or setting.value is None:
        return False
    return str(setting.value).strip().lower() in ("true", "1", "yes", "on")


async def set_mfa_required(db: AsyncSession, required: bool) -> None:
    result = await db.execute(
        select(Setting).where(Setting.key == REQUIRE_MFA_SETTING)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = "true" if required else "false"
    else:
        db.add(Setting(
            key=REQUIRE_MFA_SETTING,
            value="true" if required else "false",
            description="Require all admin portal accounts to enrol in two-factor authentication",
        ))
    await db.commit()


def is_enrolled(user: User) -> bool:
    """True once the user has proved they can generate a valid code."""
    return bool(user.totp_enabled and user.totp_verified and user.totp_secret)


async def begin_enrolment(db: AsyncSession, user: User) -> dict:
    """Create a fresh secret + backup codes. Not active until verified.

    Re-enrolling replaces any previous secret, so a user who lost their
    authenticator can start over (their old codes stop working immediately,
    which is the point).
    """
    _require_pyotp()

    secret = pyotp.random_base32()
    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name=ISSUER,
    )
    backup_codes = generate_backup_codes()

    user.totp_secret = encrypt_data(secret)
    user.totp_backup_codes = encrypt_data(json.dumps(backup_codes))
    user.totp_enabled = False   # not enforced until the code is verified
    user.totp_verified = False
    await db.commit()

    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "backup_codes": backup_codes,
    }


async def confirm_enrolment(db: AsyncSession, user: User, code: str) -> bool:
    """Verify the first code from the authenticator and switch MFA on."""
    _require_pyotp()

    if not user.totp_secret:
        return False

    try:
        totp = pyotp.TOTP(decrypt_data(user.totp_secret))
    except Exception:
        return False

    # valid_window=1 tolerates one 30s step of clock skew either way.
    if not totp.verify(code, valid_window=1):
        return False

    user.totp_enabled = True
    user.totp_verified = True
    user.totp_enrolled_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def verify_code(db: AsyncSession, user: User, code: str) -> bool:
    """Verify a login code: either a 6-digit TOTP or an 8-char backup code."""
    _require_pyotp()

    if not is_enrolled(user):
        return False

    code = (code or "").strip().replace(" ", "")
    if not code:
        return False

    try:
        totp = pyotp.TOTP(decrypt_data(user.totp_secret))
        if totp.verify(code, valid_window=1):
            return True
    except Exception:
        pass

    if len(code) == BACKUP_CODE_LENGTH:
        return await _consume_backup_code(db, user, code)

    return False


async def _consume_backup_code(db: AsyncSession, user: User, code: str) -> bool:
    """Backup codes are single use — a match removes it before returning."""
    if not user.totp_backup_codes:
        return False

    try:
        codes = json.loads(decrypt_data(user.totp_backup_codes))
    except Exception:
        return False

    code_upper = code.upper()
    if code_upper not in codes:
        return False

    codes.remove(code_upper)
    user.totp_backup_codes = encrypt_data(json.dumps(codes))
    await db.commit()
    return True


async def remaining_backup_codes(user: User) -> int:
    if not user.totp_backup_codes:
        return 0
    try:
        return len(json.loads(decrypt_data(user.totp_backup_codes)))
    except Exception:
        return 0


async def regenerate_backup_codes(db: AsyncSession, user: User) -> list[str]:
    """Issue a fresh set, invalidating every previous code."""
    codes = generate_backup_codes()
    user.totp_backup_codes = encrypt_data(json.dumps(codes))
    await db.commit()
    return codes


async def disable_mfa(db: AsyncSession, user: User) -> None:
    user.totp_enabled = False
    user.totp_verified = False
    user.totp_secret = None
    user.totp_backup_codes = None
    user.totp_enrolled_at = None
    await db.commit()


def build_qr_data_uri(provisioning_uri: str) -> Optional[str]:
    """Render the provisioning URI as an inline PNG data URI.

    Done server-side so the secret never has to reach a third-party QR service,
    and so the frontend needs no QR dependency. Returns None if qrcode is
    missing — the UI falls back to showing the secret for manual entry.
    """
    try:
        import io
        import base64
        import qrcode

        img = qrcode.make(provisioning_uri)
        buf = io.BytesIO()
        # Without Pillow installed, qrcode falls back to its pure-Python PNG
        # writer, whose save() takes no `format` kwarg — and it already only
        # emits PNG. Pillow's does take one, so try it and fall back.
        try:
            img.save(buf, format="PNG")
        except TypeError:
            img.save(buf)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None
