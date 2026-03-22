"""Tests for certificate service."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

from app.services.certificate_service import (
    request_letsencrypt_certificate,
    renew_certificate,
    check_expiring_certificates,
    validate_certificate_pem,
)
from app.models.certificate import Certificate


class TestRequestLetsEncryptCertificate:
    """Tests for requesting Let's Encrypt certificates."""

    @pytest.mark.asyncio
    async def test_cert_not_found(self, db_session):
        success, msg = await request_letsencrypt_certificate(db_session, "nonexistent")
        assert success is False
        assert "not found" in msg.lower()

    @pytest.mark.asyncio
    async def test_not_letsencrypt_cert(self, db_session):
        cert = Certificate(
            id="test-cert-1",
            name="Custom Cert",
            domain_names=["example.com"],
            certificate="PEM",
            certificate_key="KEY",
            is_letsencrypt=False,
            status="valid",
        )
        db_session.add(cert)
        await db_session.commit()

        success, msg = await request_letsencrypt_certificate(db_session, "test-cert-1")
        assert success is False
        assert "not a let's encrypt" in msg.lower()

    @pytest.mark.asyncio
    async def test_certbot_success(self, db_session):
        cert = Certificate(
            id="test-cert-2",
            name="LE Cert",
            domain_names=["test.example.com"],
            is_letsencrypt=True,
            letsencrypt_email="test@example.com",
            status="pending",
        )
        db_session.add(cert)
        await db_session.commit()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"

        with patch("subprocess.run", return_value=mock_result), \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", MagicMock(side_effect=[
                 MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="CERT_PEM"))),
                           __exit__=MagicMock(return_value=False)),
                 MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="KEY_PEM"))),
                           __exit__=MagicMock(return_value=False)),
             ])):
            success, msg = await request_letsencrypt_certificate(db_session, "test-cert-2")

        assert success is True
        assert "success" in msg.lower()

    @pytest.mark.asyncio
    async def test_certbot_failure(self, db_session):
        cert = Certificate(
            id="test-cert-3",
            name="LE Cert",
            domain_names=["fail.example.com"],
            is_letsencrypt=True,
            letsencrypt_email="test@example.com",
            status="pending",
        )
        db_session.add(cert)
        await db_session.commit()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Rate limited"

        with patch("subprocess.run", return_value=mock_result):
            success, msg = await request_letsencrypt_certificate(db_session, "test-cert-3")

        assert success is False
        assert "Rate limited" in msg

    @pytest.mark.asyncio
    async def test_certbot_timeout(self, db_session):
        import subprocess
        cert = Certificate(
            id="test-cert-4",
            name="LE Cert",
            domain_names=["timeout.example.com"],
            is_letsencrypt=True,
            letsencrypt_email="test@example.com",
            status="pending",
        )
        db_session.add(cert)
        await db_session.commit()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("certbot", 300)):
            success, msg = await request_letsencrypt_certificate(db_session, "test-cert-4")

        assert success is False
        assert "timed out" in msg.lower()


class TestRenewCertificate:
    """Tests for renewing certificates."""

    @pytest.mark.asyncio
    async def test_renew_not_found(self, db_session):
        success, msg = await renew_certificate(db_session, "nonexistent")
        assert success is False
        assert "not found" in msg.lower()

    @pytest.mark.asyncio
    async def test_renew_not_letsencrypt(self, db_session):
        cert = Certificate(
            id="test-renew-1",
            name="Custom",
            domain_names=["example.com"],
            is_letsencrypt=False,
            status="valid",
        )
        db_session.add(cert)
        await db_session.commit()

        success, msg = await renew_certificate(db_session, "test-renew-1")
        assert success is False

    @pytest.mark.asyncio
    async def test_renew_success(self, db_session):
        cert = Certificate(
            id="test-renew-2",
            name="LE Cert",
            domain_names=["renew.example.com"],
            is_letsencrypt=True,
            letsencrypt_email="test@example.com",
            status="valid",
        )
        db_session.add(cert)
        await db_session.commit()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result), \
             patch("builtins.open", MagicMock(side_effect=[
                 MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="NEW_CERT"))),
                           __exit__=MagicMock(return_value=False)),
                 MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="NEW_KEY"))),
                           __exit__=MagicMock(return_value=False)),
             ])):
            success, msg = await renew_certificate(db_session, "test-renew-2")

        assert success is True
        assert "renewed" in msg.lower()


class TestCheckExpiringCertificates:
    """Tests for finding expiring certificates."""

    @pytest.mark.asyncio
    async def test_no_expiring_certs(self, db_session):
        result = await check_expiring_certificates(db_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_find_expiring_cert(self, db_session):
        cert = Certificate(
            id="test-expiring",
            name="Expiring Cert",
            domain_names=["expire.example.com"],
            is_letsencrypt=True,
            auto_renew=True,
            status="valid",
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
        db_session.add(cert)
        await db_session.commit()

        results = await check_expiring_certificates(db_session, days_before_expiry=30)
        assert len(results) == 1
        assert results[0].id == "test-expiring"

    @pytest.mark.asyncio
    async def test_non_expiring_cert_not_included(self, db_session):
        cert = Certificate(
            id="test-not-expiring",
            name="Good Cert",
            domain_names=["good.example.com"],
            is_letsencrypt=True,
            auto_renew=True,
            status="valid",
            expires_at=datetime.now(timezone.utc) + timedelta(days=60),
        )
        db_session.add(cert)
        await db_session.commit()

        results = await check_expiring_certificates(db_session, days_before_expiry=30)
        assert len(results) == 0


class TestValidateCertificatePem:
    """Tests for certificate PEM validation."""

    def test_invalid_certificate_pem(self):
        is_valid, error, expiry = validate_certificate_pem("not-a-cert", "not-a-key")
        assert is_valid is False
        assert error is not None

    def test_empty_pem(self):
        is_valid, error, expiry = validate_certificate_pem("", "")
        assert is_valid is False
