"""Usuarios y roles (D-003, D-004)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String
from sqlmodel import Field

from app.core.base import TimestampedModel, enum_type


class UserRole(StrEnum):
    """Roles del sistema.

    - `superadmin`: todo lo de `admin` + credenciales de proveedores LLM, tools HTTP y
      usuarios. Superficie sensible, separada a propósito de la gestión de contenido.
    - `admin`: gestión de contenido (máquinas, módulos, lecciones, quizzes). Panel Angular.
    - `trainee`: consumidor de contenido en la app Flutter. No accede al backoffice.
      Es el rol del usuario demo; no se gestiona desde el panel en esta fase.
    """

    superadmin = "superadmin"
    admin = "admin"
    trainee = "trainee"

    @property
    def is_backoffice(self) -> bool:
        return self in (UserRole.superadmin, UserRole.admin)


class User(TimestampedModel, table=True):
    __tablename__ = "users"

    email: str = Field(sa_type=String(255), unique=True, index=True, nullable=False)
    full_name: str = Field(sa_type=String(160), nullable=False)
    # Nullable: el usuario demo no tiene contraseña (entra por bypass). Un hash vacío
    # sería peor: parecería una credencial válida ante un `verify_password`.
    hashed_password: str | None = Field(default=None, sa_type=String(255))
    role: UserRole = Field(
        default=UserRole.trainee, sa_type=enum_type(UserRole), index=True, nullable=False
    )

    is_active: bool = Field(default=True, nullable=False)
    # Marca el usuario compartido de demostración. Permite excluirlo de métricas y
    # borrarlo de un tirón cuando se retire el bypass.
    is_demo: bool = Field(default=False, index=True, nullable=False)

    # Datos de contexto del profesional. Sin PHI: son datos del usuario, no del paciente.
    specialty: str | None = Field(default=None, sa_type=String(120))
    institution: str | None = Field(default=None, sa_type=String(160))

    last_login_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
