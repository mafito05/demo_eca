"""Cifrado simétrico de secretos en reposo (D-008).

Se usa para las API keys de los proveedores LLM y para las cabeceras de
autenticación de las tools HTTP. La clave (`SECRET_ENCRYPTION_KEY`) es distinta de
`JWT_SECRET_KEY` a propósito: rotar la firma de tokens no debe obligar a
re-cifrar la base de datos, ni al contrario.

Para migrar a KMS/Vault basta reimplementar `encrypt`/`decrypt` manteniendo la firma.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretDecryptionError(RuntimeError):
    """El secreto no se pudo descifrar: clave rotada, dato corrupto o cifrado con otra clave."""


@lru_cache
def _fernet() -> Fernet:
    key = settings.SECRET_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY no está configurada. Generar con: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY no es una clave Fernet válida (32 bytes base64url)."
        ) from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError(
            "Could not decrypt the secret. Did SECRET_ENCRYPTION_KEY change since it was stored?"
        ) from exc


def mask(secret: str, visible: int = 4) -> str:
    """Representación segura para la API/panel: `sk-…a1b2`.

    Nunca se devuelve un secreto en claro por la API, ni al superadmin. Si se pierde,
    se sustituye.
    """
    if not secret:
        return ""
    tail = secret[-visible:] if len(secret) > visible else ""
    return f"{'•' * 8}{tail}"
