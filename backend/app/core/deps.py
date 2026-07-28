"""Dependencias compartidas de FastAPI: sesión, usuario autenticado y RBAC."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import TokenType, decode_token
from app.modules.auth.models import User, UserRole

# auto_error=False para poder devolver un 401 con nuestro propio cuerpo de error.
bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    if credentials is None:
        raise _CREDENTIALS_ERROR
    try:
        payload = decode_token(credentials.credentials, TokenType.access)
        user_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise _CREDENTIALS_ERROR from None

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """Factoría de dependencias de autorización.

    Uso: `dependencies=[Depends(require_roles(UserRole.superadmin))]`
    """

    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission for this operation.",
            )
        return user

    return _guard


# Atajos legibles para los routers.
require_backoffice = require_roles(UserRole.superadmin, UserRole.admin)
require_superadmin = require_roles(UserRole.superadmin)


async def get_user_from_token(session: AsyncSession, token: str) -> User | None:
    """Autenticación para WebSockets.

    Los WebSockets del navegador no permiten cabeceras personalizadas en el handshake, así
    que el token viaja como query param. Es aceptable porque va sobre TLS y el token es de
    vida corta, pero conviene saber que puede acabar en logs de proxies intermedios.
    """
    try:
        payload = decode_token(token, TokenType.access)
        user = await session.get(User, uuid.UUID(payload["sub"]))
    except (InvalidTokenError, KeyError, ValueError):
        return None
    if user is None or not user.is_active:
        return None
    return user
