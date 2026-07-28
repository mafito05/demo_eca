"""Piezas comunes a todos los modelos."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


def enum_type(enum_cls: type[enum.Enum], length: int = 32) -> SAEnum:
    """Tipo de columna para los enums del dominio.

    Combinación deliberada:

    - `native_enum=False`: se almacena como VARCHAR con un CHECK, no como un TYPE nativo de
      Postgres. Añadir un valor a un enum nativo requiere `ALTER TYPE`, que no es reversible
      dentro de una transacción y complica las migraciones.
    - **Pero sigue siendo un `Enum` de SQLAlchemy**, no un `String` pelado. Esa es la
      diferencia clave: SQLAlchemy convierte el valor de vuelta al miembro del enum al leer
      de la base de datos. Con `String`, los modelos de SQLModel devuelven `str` crudo (no
      revalidan al cargar de BD) y cualquier `objeto.campo.value` o `campo is Enum.x` revienta
      o falla en silencio.
    - `values_callable`: persiste el *valor* del miembro y no su nombre, de modo que lo que
      hay en la columna coincide con lo que viaja por la API.
    - `create_constraint=False` (el valor por defecto, explícito aquí para que sea una
      decisión y no un descuido): no se emite un CHECK en la tabla. SQLAlchemy ya valida al
      escribir, así que el CHECK solo protegería frente a SQL ejecutado por fuera de la
      aplicación, a cambio de que añadir un valor al enum exija migrar la restricción.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


def utcnow() -> datetime:
    """Siempre timezone-aware. Guardar naïve en una plataforma multi-zona es una fuente
    silenciosa de bugs en certificados y progreso."""
    return datetime.now(UTC)


class UUIDModel(SQLModel):
    """PK UUID v4.

    Se prefiere a un entero autoincremental porque los IDs viajan a la app móvil y al
    panel: un secuencial filtra volumen de catálogo y permite enumerar recursos.
    """

    # Sin `index=True`: la clave primaria ya crea su propio índice único.
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class TimestampedModel(UUIDModel):
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
        nullable=False,
    )
