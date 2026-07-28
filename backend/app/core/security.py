"""JWT y hashing de contraseñas.

Se usa `bcrypt` directamente en lugar de passlib: passlib está sin mantenimiento activo
y su backend de bcrypt rompe con bcrypt>=4.1.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import settings

# bcrypt trunca silenciosamente en 72 bytes; cortamos explícitamente para que el
# comportamiento sea visible y determinista.
_BCRYPT_MAX_BYTES = 72


class TokenType(StrEnum):
    access = "access"
    refresh = "refresh"
    # Token de reproducción de video (D-011). Existe porque un reproductor HLS pide docenas
    # de segmentos y no puede adjuntar la cabecera Authorization en cada uno: ni ExoPlayer ni
    # AVPlayer garantizan propagar cabeceras a las peticiones derivadas del playlist. El
    # token va en la URL, está limitado a un único asset y caduca pronto.
    playback = "playback"


def hash_password(password: str) -> str:
    payload = password.encode()[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:_BCRYPT_MAX_BYTES], hashed.encode())
    except ValueError:
        # Hash malformado en BD: se trata como credencial inválida, no como error 500.
        return False


def create_token(
    subject: str | uuid.UUID,
    token_type: TokenType = TokenType.access,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    if token_type is TokenType.access:
        expires = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    elif token_type is TokenType.playback:
        expires = now + timedelta(seconds=settings.HLS_TOKEN_TTL_SECONDS)
    else:
        expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    claims: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: TokenType = TokenType.access) -> dict[str, Any]:
    """Devuelve los claims o lanza `InvalidTokenError`.

    Valida el tipo de token: un refresh token no debe servir para acceder a recursos.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Se esperaba un token de tipo '{expected_type.value}'.")
    return payload
