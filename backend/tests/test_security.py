"""Unit tests for hashing, JWT, and the role hierarchy — no DB required."""

import jwt as pyjwt
import pytest

from app.core.security import (
    Role,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.settings import Settings


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        JWT_SECRET="unit-test-secret", JWT_ALGORITHM="HS256", JWT_ACCESS_TOKEN_EXPIRE_MINUTES=5
    )


def test_password_hash_roundtrip():
    h = hash_password("รหัสผ่านทดสอบ-123")
    assert h != "รหัสผ่านทดสอบ-123"
    assert verify_password("รหัสผ่านทดสอบ-123", h)
    assert not verify_password("wrong", h)


def test_verify_password_bad_hash_is_false_not_error():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_token_roundtrip(settings):
    token = create_access_token("auditor1", Role.SENIOR_AUDITOR, settings)
    payload = decode_access_token(token, settings)
    assert payload["sub"] == "auditor1"
    assert payload["role"] == "SENIOR_AUDITOR"
    assert payload["exp"] > payload["iat"]


def test_expired_token_rejected():
    expired = Settings(JWT_SECRET="unit-test-secret", JWT_ACCESS_TOKEN_EXPIRE_MINUTES=-1)
    token = create_access_token("auditor1", Role.AUDITOR, expired)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(token, expired)


def test_tampered_secret_rejected(settings):
    token = create_access_token("auditor1", Role.AUDITOR, settings)
    other = Settings(JWT_SECRET="a-different-secret")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token, other)


def test_role_hierarchy():
    assert Role.ADMIN.rank > Role.SENIOR_AUDITOR.rank > Role.AUDITOR.rank
