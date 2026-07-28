"""Catálogo de equipos médicos y su vínculo con el mundo físico vía QR (D-002)."""

from __future__ import annotations

import secrets
from enum import StrEnum

from sqlalchemy import String, Text
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

    # Claves de objeto en MinIO (no URLs: las URLs se firman al vuelo y caducan).
    cover_image_key: str | None = Field(default=None, sa_type=String(512))

    status: PublishStatus = Field(
        default=PublishStatus.draft,
        sa_type=enum_type(PublishStatus, 16),
        index=True,
        nullable=False,
    )
