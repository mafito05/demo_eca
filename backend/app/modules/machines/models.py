"""Catálogo de equipos médicos y su vínculo con el mundo físico vía QR (D-002)."""

from __future__ import annotations

import secrets
import uuid
from enum import StrEnum

from sqlalchemy import String, Text, UniqueConstraint
from sqlmodel import Field

from app.core.base import TimestampedModel, enum_type

# Longitud del token del QR. 12 caracteres base62 ≈ 71 bits: no enumerable por fuerza
# bruta y sigue caben en un QR pequeño imprimible sobre una máquina.
QR_TOKEN_BYTES = 9


def generate_qr_token() -> str:
    return secrets.token_urlsafe(QR_TOKEN_BYTES)


class Specialty(StrEnum):
    urologia = "urologia"
    trauma = "trauma"
    cardiologia = "cardiologia"
    neurocirugia = "neurocirugia"
    otro = "otro"


class PublishStatus(StrEnum):
    """El contenido se edita en borrador y se publica de forma explícita.

    Sin esto, un admin editando una lección la rompe en vivo para los usuarios que la
    estén viendo.
    """

    draft = "draft"
    published = "published"
    archived = "archived"


class MachineImageRole(StrEnum):
    """La portada es una imagen más, no un mecanismo aparte.

    Con un campo `cover_image_key` en la máquina y una tabla para el resto habría dos formas de
    guardar una imagen, dos de construir su URL y dos de borrarla — y "promociona esta foto a
    portada" sería copiar una clave entre sitios en lugar de cambiar una etiqueta.
    """

    cover = "cover"
    gallery = "gallery"


class MachineImage(TimestampedModel, table=True):
    """Foto de un equipo: la portada del catálogo o una de la galería de demostración.

    Tabla propia y no una columna JSON en `machine_models`, por dos motivos concretos:

    1. Cada imagen necesita identidad para poder borrarla o reordenarla sola. Con una lista
       dentro de una fila, borrar la tercera obliga a leer-modificar-escribir toda la lista, y
       dos pestañas del panel abiertas a la vez se pisan.
    2. Un JSON editado *en sitio* (`imagenes[0]["alt"] = ...`) no marca la fila como sucia en
       SQLAlchemy y el cambio se pierde sin error. `VideoAsset.renditions` se libra de eso solo
       porque el worker reasigna la lista entera de una vez.
    """

    __tablename__ = "machine_images"
    __table_args__ = (
        UniqueConstraint("machine_model_id", "order_index", name="uq_machine_image_order"),
    )

    machine_model_id: uuid.UUID = Field(foreign_key="machine_models.id", index=True, nullable=False)

    # Clave del objeto en el bucket PÚBLICO, no una URL: el host cambia entre entornos y la URL
    # se compone al leer con `storage.public_url` (D-032).
    object_key: str = Field(default="", sa_type=String(512), nullable=False)
    original_filename: str = Field(sa_type=String(255), nullable=False)
    content_type: str = Field(sa_type=String(64), nullable=False)
    size_bytes: int | None = Field(default=None)
    alt_text: str | None = Field(default=None, sa_type=String(255))
    order_index: int = Field(default=0, nullable=False)

    role: MachineImageRole = Field(
        default=MachineImageRole.gallery,
        sa_type=enum_type(MachineImageRole, 16),
        nullable=False,
    )

    # False hasta que se confirma que el PUT prefirmado llegó a MinIO. La fila nace antes que
    # el objeto —igual que `VideoAsset` nace con `source_key=""`— y una imagen a medio subir no
    # se le enseña a nadie: sería un hueco roto en el catálogo.
    is_ready: bool = Field(default=False, nullable=False)


class MachineModel(TimestampedModel, table=True):
    """Un **modelo** de equipo (no una unidad física).

    El QR se imprime N veces, una por cada máquina igual, y todas llevan al mismo
    tutorial. Cuando se necesite trazabilidad por unidad (serial/sede) se añade
    `MachineUnit` apuntando aquí; el resolver de QR absorbe el cambio. Ver D-002.
    """

    __tablename__ = "machine_models"

    # Código interno de la compañía (ej. "URO-LITHO-3000"). Es el identificador que usa
    # el negocio y el que se exporta a otros softwares junto al QR.
    code: str = Field(sa_type=String(64), unique=True, index=True, nullable=False)
    name: str = Field(sa_type=String(200), nullable=False)
    manufacturer: str | None = Field(default=None, sa_type=String(160))
    specialty: Specialty = Field(
        default=Specialty.otro, sa_type=enum_type(Specialty), index=True, nullable=False
    )
    description: str | None = Field(default=None, sa_type=Text)

    # Token opaco embebido en el QR. Único e indexado: es la ruta caliente de la app.
    qr_token: str = Field(
        default_factory=generate_qr_token,
        sa_type=String(32),
        unique=True,
        index=True,
        nullable=False,
    )

    # La portada vive en `MachineImage` con `role=cover`, no aquí: ver el docstring de
    # `MachineImageRole`. La antigua columna `cover_image_key` se eliminó en la migración de
    # imágenes de producto; nunca llegó a exponerse en ningún endpoint.

    status: PublishStatus = Field(
        default=PublishStatus.draft,
        sa_type=enum_type(PublishStatus, 16),
        index=True,
        nullable=False,
    )
