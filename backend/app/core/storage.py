"""Cliente de MinIO (S3).

El SDK de MinIO es sincrono. En los endpoints se usa solo para operaciones de metadatos y
para *firmar* URLs, que son cálculos locales sin red — no bloquean el event loop de forma
significativa. Las subidas y descargas reales de bytes ocurren en el worker (o directamente
entre el cliente y MinIO mediante URL pre-firmada, D-010).
"""

from __future__ import annotations

import io
from datetime import timedelta
from functools import lru_cache
from urllib.parse import quote

from minio import Minio

from app.core.config import settings


@lru_cache
def get_client() -> Minio:
    """Cliente para operaciones servidor-a-servidor (leer, escribir, listar)."""
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ROOT_USER,
        secret_key=settings.MINIO_ROOT_PASSWORD,
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
    )


@lru_cache
def get_presign_client() -> Minio:
    """Cliente separado, apuntando al host público, solo para firmar URLs.

    Dos detalles imprescindibles, ambos aprendidos por las malas:

    1. **No se puede firmar con `minio:9000` y reescribir el host después.** La firma SigV4
       cubre la cabecera `Host`, así que al cambiarlo la firma deja de validar. Hay que firmar
       directamente contra el host que usará el cliente final.
    2. **`region` es obligatorio aquí.** Sin región explícita, el SDK de MinIO hace una
       llamada de red real (`GET /bucket?location=`) para descubrirla antes de firmar — y este
       cliente apunta a un host que el backend NO alcanza (`localhost:9000` es el host, no el
       contenedor). El resultado era un `Connection refused` al pedir una URL de subida, con
       una traza que apuntaba a urllib3 y no daba ninguna pista del motivo real.
    """
    return Minio(
        settings.minio_public_endpoint,
        access_key=settings.MINIO_ROOT_USER,
        secret_key=settings.MINIO_ROOT_PASSWORD,
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
    )


def presign_put(bucket: str, object_key: str, ttl_seconds: int | None = None) -> str:
    """URL para que el panel suba un fichero directamente a MinIO (D-010)."""
    ttl = ttl_seconds or settings.MINIO_PRESIGN_TTL_SECONDS
    return get_presign_client().presigned_put_object(
        bucket, object_key, expires=timedelta(seconds=ttl)
    )


def presign_get(bucket: str, object_key: str, ttl_seconds: int | None = None) -> str:
    """URL de descarga temporal: segmentos HLS, certificados, manuales."""
    ttl = ttl_seconds or settings.MINIO_PRESIGN_TTL_SECONDS
    return get_presign_client().presigned_get_object(
        bucket, object_key, expires=timedelta(seconds=ttl)
    )


def public_url(object_key: str, bucket: str | None = None) -> str:
    """URL directa a un objeto del bucket público. NO va firmada y NO caduca.

    `minio-init` crea `demoeca-public` con `mc anonymous set download`, que concede
    `s3:GetObject` anónimo — pero **no** `ListBucket`: las claves (UUIDs) no son enumerables.

    Por qué aquí no se firma, a diferencia del video (D-011): una URL prefirmada caduca a la
    hora, así que el `<img>` de un catálogo abierto se rompería solo, sin que nadie tocara nada.
    Ese es justo el tipo de fallo que hace parecer rota la aplicación. Una foto de producto no
    necesita protección; un manual sí, y por eso los manuales siguen en `demoeca-docs` con
    `presign_get`.

    Se compone contra `minio_public_endpoint` por el mismo motivo que `get_presign_client`
    (D-018, D-032): esta URL la resuelve un navegador o un móvil, no el backend, y para el
    backend el host es `minio:9000`.
    """
    scheme = "https" if settings.MINIO_SECURE else "http"
    host = settings.minio_public_endpoint
    # `safe="/"` conserva la jerarquía de la clave y escapa el resto (espacios, acentos).
    return (
        f"{scheme}://{host}/{bucket or settings.MINIO_BUCKET_PUBLIC}/{quote(object_key, safe='/')}"
    )


def download_bytes(bucket: str, object_key: str) -> bytes:
    """Descarga completa en memoria. Solo para documentos (manuales PDF), nunca para video."""
    response = get_client().get_object(bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def upload_bytes(bucket: str, object_key: str, data: bytes, content_type: str) -> str:
    get_client().put_object(
        bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_key


def object_exists(bucket: str, object_key: str) -> bool:
    from minio.error import S3Error

    try:
        get_client().stat_object(bucket, object_key)
        return True
    except S3Error:
        return False
