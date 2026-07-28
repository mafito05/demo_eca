"""Servido de HLS con URLs firmadas (D-011).

El problema: el bucket de video es privado, y un reproductor HLS pide una playlist maestra,
luego una playlist por calidad y luego docenas de segmentos `.ts`. No se puede exigir la
cabecera `Authorization` en todas esas peticiones — ni ExoPlayer (Android) ni AVPlayer (iOS)
garantizan propagar las cabeceras de la petición inicial a las derivadas del playlist.

La solución aquí:

1. La app pide `master.m3u8` **con su JWT normal**. El backend comprueba permisos una vez.
2. El backend devuelve la playlist con las URIs **reescritas** para que apunten a sus propios
   endpoints, llevando un `token` de reproducción de vida corta ligado a ese único asset.
3. Las playlists de variante se reescriben igual.
4. Los segmentos **no se proxifican**: se responde `307` hacia una URL prefirmada de MinIO.
   Los bytes van del almacenamiento al dispositivo sin pasar por FastAPI. Proxificar cientos
   de megabytes por el API es la forma más rápida de tumbarlo.

Limitación conocida y aceptada para la demo: un token de reproducción filtrado da acceso a
ese video durante `HLS_TOKEN_TTL_SECONDS`. En producción esto se sustituye por un CDN con
signed cookies, que además elimina el salto de redirección por segmento.
"""

from __future__ import annotations

import re
import uuid

from app.core.config import settings
from app.core.security import TokenType, create_token
from app.core.storage import download_bytes, presign_get

# Nombres válidos de variante y de segmento tal como los genera ffmpeg: `v360p`,
# `segment003.ts`. Ojo: la variante lleva el NOMBRE de la rendition, no su índice, porque
# `var_stream_map` incluye `name:` y ffmpeg expande `%v` con él (ver workers/tasks/video.py).
#
# Se validan con lista blanca porque estos valores llegan desde la URL y se concatenan a una
# clave de objeto: sin esto, `..%2f..%2fdocs%2fmanual.pdf` leería otro bucket.
VARIANT_RE = re.compile(r"^v[0-9a-z]{2,8}$")
SEGMENT_RE = re.compile(r"^segment\d{1,6}\.ts$")
PLAYLIST_NAME = "playlist.m3u8"


class InvalidHLSPath(ValueError):
    """La variante o el segmento pedidos no encajan con el patrón esperado."""


def create_playback_token(video_asset_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Token acotado a un asset concreto.

    `sub` es el usuario (para auditoría) y `asset` limita el alcance: un token de una lección
    no sirve para otra. Sin el claim `asset`, el token sería una llave maestra de la
    videoteca.
    """
    return create_token(
        user_id,
        TokenType.playback,
        {"asset": str(video_asset_id)},
    )


def verify_playback_token(token: str, video_asset_id: uuid.UUID) -> bool:
    from jwt.exceptions import InvalidTokenError

    from app.core.security import decode_token

    try:
        claims = decode_token(token, TokenType.playback)
    except InvalidTokenError:
        return False
    return claims.get("asset") == str(video_asset_id)


def _base_path(video_asset_id: uuid.UUID) -> str:
    return f"{settings.API_V1_PREFIX}/lms/videos/{video_asset_id}/hls"


def rewrite_master_playlist(content: str, video_asset_id: uuid.UUID, token: str) -> str:
    """Reescribe `v0/playlist.m3u8` -> `/api/v1/lms/videos/{id}/hls/v0/playlist.m3u8?token=...`

    Se reescriben solo las líneas que no empiezan por `#`: en HLS, toda línea que no es una
    etiqueta es un URI.
    """
    base = _base_path(video_asset_id)
    lines: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue
        # `v0/playlist.m3u8`
        variant = stripped.split("/")[0]
        if VARIANT_RE.match(variant):
            lines.append(f"{base}/{variant}/{PLAYLIST_NAME}?token={token}")
        else:
            # Formato inesperado: se deja tal cual antes que romper la playlist entera.
            lines.append(line)

    return "\n".join(lines) + "\n"


def rewrite_variant_playlist(
    content: str, video_asset_id: uuid.UUID, variant: str, token: str
) -> str:
    """Reescribe `segment000.ts` -> `/api/v1/lms/videos/{id}/hls/v0/segment000.ts?token=...`"""
    base = _base_path(video_asset_id)
    lines: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue
        if SEGMENT_RE.match(stripped):
            lines.append(f"{base}/{variant}/{stripped}?token={token}")
        else:
            lines.append(line)

    return "\n".join(lines) + "\n"


def fetch_master(hls_master_key: str, video_asset_id: uuid.UUID, token: str) -> str:
    raw = download_bytes(settings.MINIO_BUCKET_VIDEO, hls_master_key).decode("utf-8")
    return rewrite_master_playlist(raw, video_asset_id, token)


def fetch_variant(hls_master_key: str, video_asset_id: uuid.UUID, variant: str, token: str) -> str:
    if not VARIANT_RE.match(variant):
        raise InvalidHLSPath(f"Invalid variant: {variant!r}")

    # La playlist de variante vive junto a la maestra: `hls/{asset}/master.m3u8` -> `hls/{asset}/v0/playlist.m3u8`
    prefix = hls_master_key.rsplit("/", 1)[0]
    raw = download_bytes(settings.MINIO_BUCKET_VIDEO, f"{prefix}/{variant}/{PLAYLIST_NAME}").decode(
        "utf-8"
    )
    return rewrite_variant_playlist(raw, video_asset_id, variant, token)


def segment_redirect_url(hls_master_key: str, variant: str, segment: str) -> str:
    """URL prefirmada del segmento. Los bytes NO pasan por FastAPI."""
    if not VARIANT_RE.match(variant):
        raise InvalidHLSPath(f"Invalid variant: {variant!r}")
    if not SEGMENT_RE.match(segment):
        raise InvalidHLSPath(f"Invalid segment: {segment!r}")

    prefix = hls_master_key.rsplit("/", 1)[0]
    # TTL corto: la vida útil de un segmento es la de su descarga inmediata.
    return presign_get(
        settings.MINIO_BUCKET_VIDEO, f"{prefix}/{variant}/{segment}", ttl_seconds=300
    )
