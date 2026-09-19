"""LMS: Máquina -> Módulo -> Lección, más el pipeline de video HLS y el progreso."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, DateTime, String, Text, UniqueConstraint
from sqlmodel import Field

from app.core.base import TimestampedModel, enum_type
from app.modules.machines.models import PublishStatus


class LessonContentType(StrEnum):
    video = "video"
    pdf = "pdf"
    text = "text"


class VideoStatus(StrEnum):
    """Estados del pipeline asíncrono de transcodificación.

    `uploaded` (el fichero ya está en MinIO pero no procesado) se distingue de `queued`
    porque el panel necesita mostrar "subido, pendiente de encolar" cuando Redis está caído.
    """

    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ProgressStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


class TrainingModule(TimestampedModel, table=True):
    """Etapa de la ruta de aprendizaje de una máquina (ej. "Montaje", "Calibración")."""

    __tablename__ = "training_modules"
    __table_args__ = (UniqueConstraint("machine_model_id", "order_index", name="uq_module_order"),)

    machine_model_id: uuid.UUID = Field(foreign_key="machine_models.id", index=True, nullable=False)
    title: str = Field(sa_type=String(200), nullable=False)
    description: str | None = Field(default=None, sa_type=Text)
    order_index: int = Field(default=0, nullable=False)
    # Si es True, el usuario no puede abrir este módulo sin completar el anterior.
    requires_previous: bool = Field(default=True, nullable=False)
    status: PublishStatus = Field(
        default=PublishStatus.draft, sa_type=enum_type(PublishStatus, 16), nullable=False
    )


class VideoAsset(TimestampedModel, table=True):
    """Un fichero de video y el resultado de su transcodificación a HLS (D-010, D-011).

    Se separa de `Lesson` porque un asset tiene su propio ciclo de vida asíncrono: puede
    fallar, reintentarse o reprocesarse sin tocar la lección que lo referencia.
    """

    __tablename__ = "video_assets"

    # Equipo al que pertenece el video, asignado al subirlo. Nullable a propósito: los assets
    # anteriores a esta columna quedan "sin asignar" y se reasignan desde la biblioteca.
    #
    # La cadena VideoAsset <- Lesson -> TrainingModule -> MachineModel ya existía, pero solo
    # clasifica los videos que YA cuelgan de una lección. Los recién subidos no cuelgan de nada,
    # y son precisamente los que se pierden de vista (D-055): sin esta columna, la biblioteca no
    # puede agruparlos ni filtrarlos.
    machine_model_id: uuid.UUID | None = Field(
        default=None, foreign_key="machine_models.id", index=True
    )

    original_filename: str = Field(sa_type=String(255), nullable=False)
    # Clave del .mp4 original subido con presigned URL.
    source_key: str = Field(sa_type=String(512), nullable=False)
    size_bytes: int | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)

    status: VideoStatus = Field(
        default=VideoStatus.uploaded, sa_type=enum_type(VideoStatus, 16), index=True, nullable=False
    )
    # Clave del master.m3u8 resultante. Null hasta que el worker termina.
    hls_master_key: str | None = Field(default=None, sa_type=String(512))
    # [{"name": "720p", "bandwidth": 2800000, "playlist_key": "..."}]
    renditions: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    error_message: str | None = Field(default=None, sa_type=Text)
    processing_started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    processing_finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    # Reintentos consumidos. Evita loops infinitos con un video corrupto.
    attempts: int = Field(default=0, nullable=False)


class Lesson(TimestampedModel, table=True):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("training_module_id", "order_index", name="uq_lesson_order"),
    )

    training_module_id: uuid.UUID = Field(
        foreign_key="training_modules.id", index=True, nullable=False
    )
    title: str = Field(sa_type=String(200), nullable=False)
    content_type: LessonContentType = Field(
        default=LessonContentType.video, sa_type=enum_type(LessonContentType, 16), nullable=False
    )
    order_index: int = Field(default=0, nullable=False)

    # Solo uno de estos tres aplica, según `content_type`.
    video_asset_id: uuid.UUID | None = Field(
        default=None, foreign_key="video_assets.id", index=True
    )
    document_key: str | None = Field(default=None, sa_type=String(512))
    body: str | None = Field(default=None, sa_type=Text)

    estimated_minutes: int | None = Field(default=None)
    status: PublishStatus = Field(
        default=PublishStatus.draft, sa_type=enum_type(PublishStatus, 16), nullable=False
    )


class UserLessonProgress(TimestampedModel, table=True):
    """Progreso por usuario y lección.

    La restricción única es lo que hace idempotente el "heartbeat" que manda el player
    cada pocos segundos: se hace UPSERT sobre (user, lesson) en lugar de acumular filas.
    """

    __tablename__ = "user_lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_progress_user_lesson"),)

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    lesson_id: uuid.UUID = Field(foreign_key="lessons.id", index=True, nullable=False)

    status: ProgressStatus = Field(
        default=ProgressStatus.not_started,
        sa_type=enum_type(ProgressStatus, 16),
        index=True,
        nullable=False,
    )
    # Última posición vista, para reanudar el video donde se dejó.
    last_position_seconds: float = Field(default=0.0, nullable=False)
    # Porcentaje máximo alcanzado. Separado de la posición: rebobinar no debe reducir el
    # progreso ni permitir "completar" saltando al final.
    watched_percent: float = Field(default=0.0, nullable=False)
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
