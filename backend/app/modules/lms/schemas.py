"""Schemas del LMS.

Separación deliberada entre los schemas de **autoría** (panel Angular) y los de **consumo**
(app Flutter). No es duplicación: el trainee recibe su progreso y el estado de bloqueo del
módulo, datos que al editor de contenido no le sirven; y el editor ve el estado de publicación
y el pipeline de video, que al trainee no le importan.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.lms.models import LessonContentType, ProgressStatus, VideoStatus
from app.modules.machines.models import PublishStatus


# =============================================================================
#  Autoría (panel)
# =============================================================================
class TrainingModuleCreate(BaseModel):
    machine_model_id: uuid.UUID
    title: str = Field(max_length=200)
    description: str | None = None
    order_index: int = Field(default=0, ge=0)
    requires_previous: bool = True
    status: PublishStatus = PublishStatus.draft


class TrainingModuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    order_index: int | None = Field(default=None, ge=0)
    requires_previous: bool | None = None
    status: PublishStatus | None = None


class TrainingModuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_model_id: uuid.UUID
    title: str
    description: str | None
    order_index: int
    requires_previous: bool
    status: PublishStatus


class LessonCreate(BaseModel):
    training_module_id: uuid.UUID
    title: str = Field(max_length=200)
    content_type: LessonContentType = LessonContentType.video
    order_index: int = Field(default=0, ge=0)
    video_asset_id: uuid.UUID | None = None
    document_key: str | None = None
    body: str | None = None
    estimated_minutes: int | None = Field(default=None, ge=1)
    status: PublishStatus = PublishStatus.draft


class LessonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    content_type: LessonContentType | None = None
    order_index: int | None = Field(default=None, ge=0)
    video_asset_id: uuid.UUID | None = None
    document_key: str | None = None
    body: str | None = None
    estimated_minutes: int | None = Field(default=None, ge=1)
    status: PublishStatus | None = None


class LessonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    training_module_id: uuid.UUID
    title: str
    content_type: LessonContentType
    order_index: int
    video_asset_id: uuid.UUID | None
    estimated_minutes: int | None
    status: PublishStatus


# =============================================================================
#  Autoría: árbol completo
# =============================================================================
class LessonAuthoring(BaseModel):
    """Lección con TODOS los campos editables, para precargar el formulario del panel.

    Se distingue de `LessonInPath` (consumo) a propósito: esta lleva `body`, `document_key`,
    `video_asset_id` y el estado de publicación, y no lleva progreso.
    """

    id: uuid.UUID
    title: str
    content_type: LessonContentType
    order_index: int
    video_asset_id: uuid.UUID | None
    video_status: VideoStatus | None = Field(
        default=None, description="Status of the attached video asset, if any."
    )
    document_key: str | None
    body: str | None
    estimated_minutes: int | None
    status: PublishStatus


class ModuleAuthoring(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    order_index: int
    requires_previous: bool
    status: PublishStatus
    lessons: list[LessonAuthoring]


class AuthoringTree(BaseModel):
    machine_model_id: uuid.UUID
    machine_code: str
    machine_name: str
    machine_status: PublishStatus
    modules: list[ModuleAuthoring]


# =============================================================================
#  Pipeline de video
# =============================================================================
class VideoUploadRequest(BaseModel):
    filename: str = Field(max_length=255)
    size_bytes: int | None = Field(default=None, ge=1)


class VideoUploadTicket(BaseModel):
    """Todo lo que el panel necesita para subir el fichero sin pasar por el API (D-010)."""

    video_asset_id: uuid.UUID
    upload_url: str
    object_key: str
    expires_in_seconds: int


class VideoAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    status: VideoStatus
    duration_seconds: float | None
    renditions: list[dict]
    error_message: str | None
    attempts: int


class VideoAssetListItem(BaseModel):
    """Fila de la biblioteca de videos del panel.

    Lleva `used_by_lessons` para que el admin distinga un video en uso de uno huérfano: sin ese
    dato, reemplazar el video de una lección da miedo porque no se sabe qué más lo usa.
    """

    id: uuid.UUID
    original_filename: str
    status: VideoStatus
    duration_seconds: float | None
    error_message: str | None
    attempts: int
    created_at: datetime
    used_by_lessons: list[str]


# =============================================================================
#  Consumo (app móvil)
# =============================================================================
class LessonProgressRead(BaseModel):
    status: ProgressStatus
    last_position_seconds: float
    watched_percent: float
    completed_at: datetime | None


class ProgressUpdate(BaseModel):
    """Heartbeat del reproductor.

    El cliente manda su posición; el porcentaje lo calcula el servidor a partir de la
    duración real del video. Si el cliente pudiera fijar `watched_percent`, completar una
    lección sin verla sería un `PUT` con `100`.
    """

    position_seconds: float = Field(ge=0)


class LessonInPath(BaseModel):
    """Lección tal como la ve el trainee dentro de su ruta de aprendizaje."""

    id: uuid.UUID
    title: str
    content_type: LessonContentType
    order_index: int
    estimated_minutes: int | None
    has_video: bool
    # False si el video todavía se está transcodificando: la app muestra "procesando".
    video_ready: bool
    progress: LessonProgressRead


class ModuleInPath(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    order_index: int
    # True si el módulo anterior no está completo y este exige prerrequisito.
    locked: bool
    completed_lessons: int
    total_lessons: int
    lessons: list[LessonInPath]


class LearningPath(BaseModel):
    """Respuesta al escaneo del QR: la ruta completa con el progreso del usuario."""

    machine_model_id: uuid.UUID
    machine_name: str
    machine_code: str
    total_lessons: int
    completed_lessons: int
    progress_percent: float
    modules: list[ModuleInPath]


class LessonDetail(BaseModel):
    id: uuid.UUID
    title: str
    content_type: LessonContentType
    body: str | None
    estimated_minutes: int | None
    progress: LessonProgressRead
    duration_seconds: float | None
    # Relativa al API. Null si la lección no es de video o el video no está listo.
    hls_master_url: str | None
    document_url: str | None
