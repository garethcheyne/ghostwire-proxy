"""Admin portal two-factor authentication.

The important properties here are the ones whose failure is silent: a backup
code that can be reused, a secret stored in plaintext, or an enrolment that goes
live before the user has proved they can generate a code.
"""
import json

import pyotp
import pytest

from app.core.security import get_password_hash, decrypt_data
from app.models.user import User
from app.services import admin_mfa_service as mfa


@pytest.fixture
async def user(db_session):
    u = User(
        email="mfa-test@example.com",
        name="MFA Test",
        password_hash=get_password_hash("correct-horse"),
        role="admin",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


class TestEnrolment:
    @pytest.mark.asyncio
    async def test_new_user_is_not_enrolled(self, user):
        assert mfa.is_enrolled(user) is False

    @pytest.mark.asyncio
    async def test_setup_does_not_activate_until_verified(self, db_session, user):
        """A half-finished setup must not challenge the next login, or a user
        who closed the tab mid-enrolment is locked out."""
        await mfa.begin_enrolment(db_session, user)

        assert user.totp_secret is not None
        assert mfa.is_enrolled(user) is False

    @pytest.mark.asyncio
    async def test_wrong_code_does_not_enable(self, db_session, user):
        await mfa.begin_enrolment(db_session, user)

        assert await mfa.confirm_enrolment(db_session, user, "000000") is False
        assert mfa.is_enrolled(user) is False

    @pytest.mark.asyncio
    async def test_correct_code_enables(self, db_session, user):
        setup = await mfa.begin_enrolment(db_session, user)
        code = pyotp.TOTP(setup["secret"]).now()

        assert await mfa.confirm_enrolment(db_session, user, code) is True
        assert mfa.is_enrolled(user) is True
        assert user.totp_enrolled_at is not None

    @pytest.mark.asyncio
    async def test_secret_is_encrypted_at_rest(self, db_session, user):
        setup = await mfa.begin_enrolment(db_session, user)

        assert setup["secret"] not in user.totp_secret
        assert decrypt_data(user.totp_secret) == setup["secret"]

    @pytest.mark.asyncio
    async def test_backup_codes_are_encrypted_at_rest(self, db_session, user):
        setup = await mfa.begin_enrolment(db_session, user)

        for code in setup["backup_codes"]:
            assert code not in user.totp_backup_codes
        assert json.loads(decrypt_data(user.totp_backup_codes)) == setup["backup_codes"]

    @pytest.mark.asyncio
    async def test_issues_ten_backup_codes(self, db_session, user):
        setup = await mfa.begin_enrolment(db_session, user)

        assert len(setup["backup_codes"]) == mfa.BACKUP_CODE_COUNT
        assert len(set(setup["backup_codes"])) == mfa.BACKUP_CODE_COUNT
        assert all(len(c) == mfa.BACKUP_CODE_LENGTH for c in setup["backup_codes"])

    @pytest.mark.asyncio
    async def test_provisioning_uri_identifies_the_account(self, db_session, user):
        setup = await mfa.begin_enrolment(db_session, user)

        assert setup["provisioning_uri"].startswith("otpauth://totp/")
        assert "mfa-test%40example.com" in setup["provisioning_uri"]


class TestVerification:
    @pytest.fixture
    async def enrolled(self, db_session, user):
        setup = await mfa.begin_enrolment(db_session, user)
        await mfa.confirm_enrolment(db_session, user, pyotp.TOTP(setup["secret"]).now())
        return user, setup

    @pytest.mark.asyncio
    async def test_valid_totp_verifies(self, db_session, enrolled):
        user, setup = enrolled
        assert await mfa.verify_code(db_session, user, pyotp.TOTP(setup["secret"]).now()) is True

    @pytest.mark.asyncio
    async def test_invalid_code_rejected(self, db_session, enrolled):
        user, _ = enrolled
        assert await mfa.verify_code(db_session, user, "123456") is False

    @pytest.mark.asyncio
    async def test_empty_code_rejected(self, db_session, enrolled):
        user, _ = enrolled
        assert await mfa.verify_code(db_session, user, "") is False
        assert await mfa.verify_code(db_session, user, None) is False

    @pytest.mark.asyncio
    async def test_backup_code_works_once_only(self, db_session, enrolled):
        """The single most important property here: a replayed backup code is a
        permanent bypass of the second factor."""
        user, setup = enrolled
        code = setup["backup_codes"][0]

        assert await mfa.verify_code(db_session, user, code) is True
        assert await mfa.verify_code(db_session, user, code) is False

    @pytest.mark.asyncio
    async def test_consuming_a_backup_code_leaves_the_rest(self, db_session, enrolled):
        user, setup = enrolled
        await mfa.verify_code(db_session, user, setup["backup_codes"][0])

        assert await mfa.remaining_backup_codes(user) == mfa.BACKUP_CODE_COUNT - 1
        assert await mfa.verify_code(db_session, user, setup["backup_codes"][1]) is True

    @pytest.mark.asyncio
    async def test_backup_code_is_case_insensitive(self, db_session, enrolled):
        user, setup = enrolled
        assert await mfa.verify_code(db_session, user, setup["backup_codes"][0].lower()) is True

    @pytest.mark.asyncio
    async def test_regenerate_invalidates_previous_codes(self, db_session, enrolled):
        user, setup = enrolled
        old = setup["backup_codes"][0]

        fresh = await mfa.regenerate_backup_codes(db_session, user)

        assert len(fresh) == mfa.BACKUP_CODE_COUNT
        assert old not in fresh
        assert await mfa.verify_code(db_session, user, old) is False

    @pytest.mark.asyncio
    async def test_disable_clears_every_secret(self, db_session, enrolled):
        user, setup = enrolled
        await mfa.disable_mfa(db_session, user)

        assert mfa.is_enrolled(user) is False
        assert user.totp_secret is None
        assert user.totp_backup_codes is None
        assert await mfa.verify_code(db_session, user, setup["backup_codes"][2]) is False

    @pytest.mark.asyncio
    async def test_unenrolled_user_verifies_nothing(self, db_session, user):
        assert await mfa.verify_code(db_session, user, "123456") is False


class TestPolicy:
    @pytest.mark.asyncio
    async def test_defaults_to_not_required(self, db_session):
        assert await mfa.is_mfa_required(db_session) is False

    @pytest.mark.asyncio
    async def test_toggles_and_persists(self, db_session):
        await mfa.set_mfa_required(db_session, True)
        assert await mfa.is_mfa_required(db_session) is True

        await mfa.set_mfa_required(db_session, False)
        assert await mfa.is_mfa_required(db_session) is False


class TestQrCode:
    def test_renders_an_inline_png(self):
        uri = pyotp.TOTP(pyotp.random_base32()).provisioning_uri(
            name="a@b.c", issuer_name="Ghostwire Proxy"
        )
        data_uri = mfa.build_qr_data_uri(uri)

        assert data_uri is not None
        assert data_uri.startswith("data:image/png;base64,")

        import base64

        raw = base64.b64decode(data_uri.split(",", 1)[1])
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
