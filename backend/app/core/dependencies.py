"""FastAPI dependencies: DB session, current user, role checks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, decode_access_token
from app.core.settings import Settings, get_settings
from app.db.models import User
from app.db.session import get_session_factory

_bearer = HTTPBearer(auto_error=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ไม่ได้รับอนุญาต กรุณาเข้าสู่ระบบ",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        raise unauthorized from None
    user = (
        await session.execute(select(User).where(User.username == payload.get("sub")))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum: Role):
    """Hierarchy check: ADMIN > SENIOR_AUDITOR > AUDITOR."""

    async def _check(user: CurrentUser) -> User:
        if Role(user.role).rank < minimum.rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="สิทธิ์การใช้งานไม่เพียงพอ",
            )
        return user

    return Depends(_check)
