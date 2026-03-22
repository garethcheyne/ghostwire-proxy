"""Tests for security core module (password hashing, JWT, encryption)."""

import pytest
from datetime import timedelta
from unittest.mock import patch

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    encrypt_data,
    decrypt_data,
    hash_sensitive_data,
    _truncate_password,
)


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_hash_password(self):
        hashed = get_password_hash("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = get_password_hash("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        hash1 = get_password_hash("mypassword")
        hash2 = get_password_hash("mypassword")
        assert hash1 != hash2  # Bcrypt uses random salt

    def test_truncate_short_password(self):
        result = _truncate_password("short")
        assert result == "short"

    def test_truncate_long_password(self):
        long_pass = "a" * 100
        result = _truncate_password(long_pass)
        assert len(result.encode("utf-8")) <= 72

    def test_empty_password(self):
        hashed = get_password_hash("")
        assert verify_password("", hashed) is True


class TestJWT:
    """Tests for JWT token creation and decoding."""

    def test_create_access_token(self):
        token = create_access_token(data={"sub": "user-123"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self):
        token = create_access_token(data={"sub": "user-123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        token = create_refresh_token(data={"sub": "user-123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_access_token_with_custom_expiry(self):
        token = create_access_token(
            data={"sub": "user-123"},
            expires_delta=timedelta(hours=1),
        )
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"

    def test_decode_invalid_token(self):
        result = decode_token("invalid.token.here")
        assert result is None

    def test_decode_empty_token(self):
        result = decode_token("")
        assert result is None

    def test_token_contains_expiry(self):
        token = create_access_token(data={"sub": "user-123"})
        payload = decode_token(token)
        assert "exp" in payload

    def test_token_preserves_custom_data(self):
        token = create_access_token(data={"sub": "user-123", "role": "admin"})
        payload = decode_token(token)
        assert payload["role"] == "admin"


class TestEncryption:
    """Tests for Fernet symmetric encryption."""

    def test_encrypt_and_decrypt(self):
        plaintext = "my-secret-api-key"
        encrypted = encrypt_data(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_data(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self):
        plaintext = "same-data"
        enc1 = encrypt_data(plaintext)
        enc2 = encrypt_data(plaintext)
        assert enc1 != enc2  # Fernet uses random IV

    def test_decrypt_wrong_data(self):
        with pytest.raises(Exception):
            decrypt_data("not-valid-encrypted-data")

    def test_encrypt_empty_string(self):
        encrypted = encrypt_data("")
        decrypted = decrypt_data(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode(self):
        plaintext = "héllo wörld 🔑"
        encrypted = encrypt_data(plaintext)
        decrypted = decrypt_data(encrypted)
        assert decrypted == plaintext


class TestHashSensitiveData:
    """Tests for SHA-256 hashing."""

    def test_hash_produces_hex_digest(self):
        result = hash_sensitive_data("test")
        assert len(result) == 64  # SHA-256 hex digest

    def test_same_input_same_hash(self):
        h1 = hash_sensitive_data("test")
        h2 = hash_sensitive_data("test")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = hash_sensitive_data("test1")
        h2 = hash_sensitive_data("test2")
        assert h1 != h2
