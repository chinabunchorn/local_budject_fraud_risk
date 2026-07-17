"""Password hashing (bcrypt) and JWT access tokens for the simple RBAC.

Roles form a strict hierarchy — ADMIN > SENIOR_AUDITOR > AUDITOR — and every
dashboard read endpoint accepts any active role; the hierarchy exists for
future admin/disposition endpoints. Keycloak stays a documented upgrade path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
import jwt

from app.core.settings import Settings


class Role(StrEnum):
    ADMIN = "ADMIN"
    SENIOR_AUDITOR = "SENIOR_AUDITOR"
    AUDITOR = "AUDITOR"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK: dict[Role, int] = {Role.AUDITOR: 1, Role.SENIOR_AUDITOR: 2, Role.ADMIN: 3}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(username: str, role: Role, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict:
    """Raises jwt.InvalidTokenError (incl. ExpiredSignatureError) on any failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
