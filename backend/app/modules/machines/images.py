"""Lógica de las imágenes de producto: claves de objeto, tipos permitidos y serialización.

Vive fuera del router porque tres consumidores distintos la necesitan (el propio router de
máquinas, el catálogo y el árbol de autoría del LMS) y porque las reglas de qué se acepta como
imagen son una decisión de seguridad que conviene tener en un solo sitio.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.modules.machines.models import MachineImage, MachineImageRole
from app.modules.machines.schemas import MachineImageRead

# Tipos aceptados y la extensión con la que se guarda cada uno.
#
# SVG queda FUERA a propósito, y no por comodidad: un SVG servido desde un bucket público con
# `Content-Type: image/svg+xml` es XSS almacenado en cuanto alguien abre esa URL en una pestaña
# —un SVG puede llevar `<script>`—. Como las URLs de este bucket son públicas y permanentes, el
# riesgo no caduca.
ALLOWED_IMAGE_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def is_allowed_content_type(content_type: str) -> bool:
    return normalise_content_type(content_type) in ALLOWED_IMAGE_CONTENT_TYPES


def normalise_content_type(content_type: str) -> str:
    """Quita parámetros y espacios: `image/jpeg; charset=binary` -> `image/jpeg`."""
    return content_type.split(";")[0].strip().lower()


def object_key_for(machine_id: uuid.UUID, image_id: uuid.UUID, content_type: str) -> str:
    """Clave del objeto en el bucket público.

    La extensión se **deriva del content-type**, nunca del nombre que mandó el cliente: un
    `foto.png.exe` no debe acabar produciendo una clave con extensión ejecutable. Ambos
    componentes son UUID, así que una subida no puede pisar la imagen de otra máquina.
    """
    extension = ALLOWED_IMAGE_CONTENT_TYPES[normalise_content_type(content_type)]
    return f"machines/{machine_id}/{image_id}.{extension}"


def to_read(image: MachineImage) -> MachineImageRead:
    return MachineImageRead(
        id=image.id,
        url=public_url_for(image),
        role=image.role,
        order_index=image.order_index,
        alt_text=image.alt_text,
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        is_ready=image.is_ready,
    )


def public_url_for(image: MachineImage) -> str:
    """URL pública con sufijo de versión.

    El `?v=` es lo que hace que sustituir una foto se vea. Sin él, el navegador y el
    `ImageCache` de Flutter siguen sirviendo la versión anterior indefinidamente —la URL no ha
    cambiado— y el cambio parece no haber funcionado. Se usa `updated_at`, que Postgres refresca
    solo en cada UPDATE de la fila.
    """
    return f"{storage.public_url(image.object_key)}?v={int(image.updated_at.timestamp())}"


def to_reads(images: Iterable[MachineImage]) -> list[MachineImageRead]:
    """Solo las confirmadas: una imagen cuyo PUT nunca terminó sería un hueco roto."""
    return [to_read(image) for image in images if image.is_ready]


def cover_url(images: Iterable[MachineImage]) -> str | None:
    for image in images:
        if image.role is MachineImageRole.cover and image.is_ready:
            return public_url_for(image)
    return None


async def load_for_machines(
    session: AsyncSession, machine_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[MachineImage]]:
    """Todas las imágenes de N máquinas en UNA consulta, agrupadas por máquina.

    Existe para que el catálogo siga cumpliendo lo que promete su docstring: resolverse en un
    número fijo de consultas y no una por tarjeta.
    """
    if not machine_ids:
        return {}

    rows = (
        (
            await session.execute(
                select(MachineImage)
                .where(MachineImage.machine_model_id.in_(machine_ids))
                .order_by(MachineImage.order_index)
            )
        )
        .scalars()
        .all()
    )

    grouped: dict[uuid.UUID, list[MachineImage]] = {}
    for image in rows:
        grouped.setdefault(image.machine_model_id, []).append(image)
    return grouped
