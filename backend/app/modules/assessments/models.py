"""Quizzes, intentos y certificados."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlmodel import Field

from app.core.base import TimestampedModel, enum_type
from app.modules.machines.models import PublishStatus


def generate_certificate_code() -> str:
    """Código verificable públicamente, formato `ECA-XXXXXXXX`."""
    return f"ECA-{secrets.token_hex(4).upper()}"


class QuestionType(StrEnum):
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"
    true_false = "true_false"


class Quiz(TimestampedModel, table=True):
    """Evaluación asociada a un módulo de capacitación.

    Se cuelga del módulo y no de la máquina para permitir evaluación por etapas; un quiz
    final de máquina es simplemente el quiz del último módulo.
    """

    __tablename__ = "quizzes"

    training_module_id: uuid.UUID = Field(
        foreign_key="training_modules.id", index=True, nullable=False
    )
    title: str = Field(sa_type=String(200), nullable=False)
    description: str | None = Field(default=None, sa_type=Text)

    passing_score: int = Field(default=80, nullable=False)  # porcentaje
    max_attempts: int = Field(default=3, nullable=False)
    shuffle_questions: bool = Field(default=True, nullable=False)
    time_limit_minutes: int | None = Field(default=None)
    # Si es True, aprobar emite certificado automáticamente.
    grants_certificate: bool = Field(default=True, nullable=False)
    status: PublishStatus = Field(
        default=PublishStatus.draft, sa_type=enum_type(PublishStatus, 16), nullable=False
    )


class Question(TimestampedModel, table=True):
    __tablename__ = "questions"

    quiz_id: uuid.UUID = Field(foreign_key="quizzes.id", index=True, nullable=False)
    text: str = Field(sa_type=Text, nullable=False)
    question_type: QuestionType = Field(
        default=QuestionType.single_choice, sa_type=enum_type(QuestionType, 24), nullable=False
    )
    order_index: int = Field(default=0, nullable=False)
    points: int = Field(default=1, nullable=False)
    # Se muestra tras responder. Valor pedagógico y además material para el RAG.
    explanation: str | None = Field(default=None, sa_type=Text)


class AnswerOption(TimestampedModel, table=True):
    """Opción de respuesta.

    `is_correct` NUNCA se serializa hacia la app: el schema de lectura para el móvil lo
    excluye explícitamente. La corrección ocurre siempre en el servidor.
    """

    __tablename__ = "answer_options"

    question_id: uuid.UUID = Field(foreign_key="questions.id", index=True, nullable=False)
    text: str = Field(sa_type=Text, nullable=False)
    is_correct: bool = Field(default=False, nullable=False)
    order_index: int = Field(default=0, nullable=False)


class QuizAttempt(TimestampedModel, table=True):
    __tablename__ = "quiz_attempts"

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    quiz_id: uuid.UUID = Field(foreign_key="quizzes.id", index=True, nullable=False)
    attempt_number: int = Field(default=1, nullable=False)

    started_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    submitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    score: float | None = Field(default=None)
    passed: bool | None = Field(default=None, index=True)


class AttemptAnswer(TimestampedModel, table=True):
    """Respuesta dada por el usuario.

    Guarda los IDs de opción como JSON en lugar de tabla puente: no se consulta por
    opción seleccionada, solo se lee el intento completo para corregirlo y auditarlo.
    """

    __tablename__ = "attempt_answers"

    attempt_id: uuid.UUID = Field(foreign_key="quiz_attempts.id", index=True, nullable=False)
    question_id: uuid.UUID = Field(foreign_key="questions.id", index=True, nullable=False)
    selected_option_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    is_correct: bool = Field(default=False, nullable=False)
    points_awarded: float = Field(default=0.0, nullable=False)


class Certificate(TimestampedModel, table=True):
    """Certificado emitido al aprobar.

    El PDF se genera una vez y se guarda en MinIO; no se regenera al vuelo en cada
    descarga, para que el documento entregado sea siempre byte-idéntico al emitido.
    """

    __tablename__ = "certificates"

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    quiz_attempt_id: uuid.UUID = Field(foreign_key="quiz_attempts.id", unique=True, nullable=False)
    machine_model_id: uuid.UUID = Field(foreign_key="machine_models.id", index=True, nullable=False)

    code: str = Field(
        default_factory=generate_certificate_code,
        sa_type=String(32),
        unique=True,
        index=True,
        nullable=False,
    )
    pdf_key: str | None = Field(default=None, sa_type=String(512))
    issued_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    # Null = sin vencimiento. Reservado para recertificación periódica (ver supuesto 3).
    expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    # Datos congelados en el momento de la emisión: si luego cambia el nombre del usuario
    # o el título de la máquina, el certificado ya emitido no debe mutar.
    holder_name_snapshot: str = Field(sa_type=String(160), nullable=False)
    machine_name_snapshot: str = Field(sa_type=String(200), nullable=False)
    score_snapshot: float = Field(nullable=False)
