from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginChallengeResponse(BaseModel):
    """Returned by /auth/login when the password alone isn't enough.

    Exactly one of the token fields is populated. Neither is a session token —
    `get_current_user` rejects both, because they carry a `type` other than
    "access". They only unlock the endpoint named by `challenge`.
    """

    # "totp"  -> user is enrolled, must supply a code at /auth/login/totp
    # "enrol" -> MFA is required org-wide but this user has not enrolled yet
    challenge: str
    challenge_token: str | None = None
    enrolment_token: str | None = None
    message: str


class TotpLoginRequest(BaseModel):
    challenge_token: str
    code: str


class MfaStatusResponse(BaseModel):
    enabled: bool
    verified: bool
    enrolled_at: str | None = None
    backup_codes_remaining: int
    required_org_wide: bool


class MfaSetupResponse(BaseModel):
    """Returned once, when enrolment begins. The secret is never shown again."""

    secret: str
    provisioning_uri: str
    qr_code: str | None = None  # inline PNG data URI
    backup_codes: list[str]


class MfaVerifyRequest(BaseModel):
    code: str


class MfaVerifiedResponse(BaseModel):
    """Confirming enrolment during a forced enrolment also completes the login,
    so the tokens come back here rather than forcing a second sign-in."""

    success: bool
    message: str
    access_token: str | None = None
    refresh_token: str | None = None


class MfaDisableRequest(BaseModel):
    """Disabling requires re-proving both factors, so a walk-up attacker with an
    open session can't quietly remove it."""

    password: str
    code: str


class BackupCodesResponse(BaseModel):
    backup_codes: list[str]
