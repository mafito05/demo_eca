"""Contrato del dashboard administrativo.

Cada nombre de campo de este fichero acaba en `admin-web/src/app/core/models/api.models.ts`
(D-022), así que renombrar algo después rompe el panel. Convención fijada aquí:
sufijos `_total`, `_percent`, `_ms`, `_minutes`, y `| None` documentado en la `description`
siempre que el valor pueda venir nulo.

Dos decisiones de forma:

1. **Enums cerrados y pequeños -> campos explícitos** (`draft`/`published`/`archived`), no
   `dict[str, int]`. Así la presencia de todos los estados la garantiza Pydantic, y el panel
   recibe campos reales en vez de un índice con claves que pueden faltar.
2. **Dimensiones abiertas -> lista de filas tipadas** (`by_provider`, `by_specialty`), no dict:
   preservan el orden para los gráficos y cada fila puede llevar varias métricas.

La regla que gobierna los nulos: `None` significa "no hay datos para calcularlo". Un `0` es una
afirmación distinta ("hay datos y el valor es cero") y el panel los pinta diferente.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.modules.agent.models import DocumentSourceType
from app.modules.machines.models import Specialty


class ActionSeverity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class PendingActionCode(StrEnum):
    """Códigos estables de los avisos del dashboard.

    Son códigos y no solo texto para que el panel pueda decidir icono, color y enlace sin
    parsear el mensaje.
    """

    no_provider_credential = "no_provider_credential"
    provider_credential_check_failing = "provider_credential_check_failing"
    provider_credential_never_checked = "provider_credential_never_checked"
    no_active_agent_config = "no_active_agent_config"
    no_default_agent_config = "no_default_agent_config"
    knowledge_documents_failed = "knowledge_documents_failed"
    knowledge_documents_pending = "knowledge_documents_pending"
    knowledge_documents_stuck = "knowledge_documents_stuck"
    video_assets_failed = "video_assets_failed"
    video_assets_stuck = "video_assets_stuck"
    no_published_machine = "no_published_machine"
    published_machine_without_content = "published_machine_without_content"
    lessons_without_video_asset = "lessons_without_video_asset"
    tools_registered_none_active = "tools_registered_none_active"


# =============================================================================
#  Contenido
# =============================================================================
class SpecialtyCount(BaseModel):
    specialty: Specialty
    total: int
    published: int


class MachineCounters(BaseModel):
    total: int
    draft: int
    published: int
    archived: int
    published_without_content: int = Field(
        description="Published equipment with no published training module. Its printed QR "
        "code resolves to an empty training path."
    )
    by_specialty: list[SpecialtyCount]


class ModuleCounters(BaseModel):
    total: int
    draft: int
    published: int
    archived: int


class LessonCounters(BaseModel):
    total: int
    draft: int
    published: int
    archived: int
    video: int
    pdf: int
    text: int
    video_without_asset: int = Field(
        description="Lessons of type video with no video asset attached."
    )
    estimated_minutes_total: int


class VideoCounters(BaseModel):
    total: int
    uploaded: int
    queued: int
    processing: int
    ready: int
    failed: int
    ready_minutes: float | None = Field(
        default=None,
        description="Total duration of ready videos. Null when no duration is known: "
        "that is not the same as zero minutes of video.",
    )
    total_size_mb: float | None = Field(
        default=None, description="Total stored size. Null when no size is known."
    )


class ContentStats(BaseModel):
    machines: MachineCounters
    modules: ModuleCounters
    lessons: LessonCounters
    videos: VideoCounters


# =============================================================================
#  RAG
# =============================================================================
class SourceTypeCount(BaseModel):
    source_type: DocumentSourceType
    total: int


class KnowledgeStats(BaseModel):
    documents_total: int
    documents_pending: int
    documents_processing: int
    documents_indexed: int
    documents_failed: int
    documents_global: int = Field(
        description="Documents not scoped to a machine: visible to every piece of equipment."
    )
    documents_by_source_type: list[SourceTypeCount]
    chunks_total: int = Field(description="Actual row count in the vector table.")
    chunks_global: int
    declared_chunk_count_total: int = Field(
        description="Sum of the chunk_count column on documents. A mismatch with chunks_total "
        "is itself the signal of a half-finished ingestion, which is why both are exposed."
    )
    embedding_models: list[str]
    average_chunks_per_indexed_document: float | None = Field(
        default=None, description="Null when no document is indexed."
    )
    last_indexed_at: datetime | None = None


# =============================================================================
#  Actividad del agente
# =============================================================================
class DailyActivity(BaseModel):
    day: date
    conversations: int
    messages: int


class ProviderUsage(BaseModel):
    provider: str = Field(description='Provider key, or "unknown" when the column is null.')
    assistant_messages: int
    total_tokens: int
    avg_latency_ms: float | None = None


class LatencyStats(BaseModel):
    """Percentiles de latencia de las respuestas del agente.

    `sample_size` viaja siempre junto a los percentiles: son `percentile_disc`, así que con
    pocas muestras el valor es real pero poco representativo, y el panel necesita saberlo
    para rotular "n=3" u ocultar el dato.
    """

    sample_size: int
    p50_ms: int | None = None
    p95_ms: int | None = None
    avg_ms: float | None = None
    max_ms: int | None = None


class AgentActivityStats(BaseModel):
    window_days: int
    window_start: date = Field(description="First day of the window, in UTC.")
    window_end: date = Field(description="Last day of the window, in UTC.")
    includes_demo_traffic: bool = Field(
        default=True,
        description="Traffic from the shared demo account IS counted here: its tokens and "
        "latency are real cost and real system health.",
    )

    conversations_total: int
    conversations_in_window: int
    conversations_archived: int
    conversations_with_machine_context: int
    distinct_users_in_window: int

    messages_total: int
    messages_in_window: int
    assistant_messages_in_window: int

    prompt_tokens_total: int
    completion_tokens_total: int
    tokens_total: int

    grounded_assistant_messages: int = Field(
        description="Assistant answers that cited at least one retrieved source."
    )
    grounded_answer_percent: float | None = Field(
        default=None, description="Null when there were no assistant messages in the window."
    )

    tool_invocations_in_window: int
    latency: LatencyStats
    by_provider: list[ProviderUsage]
    daily: list[DailyActivity] = Field(
        description="Exactly window_days contiguous entries, oldest first. Days with no "
        "activity are present with zeros."
    )


# =============================================================================
#  Salud del sistema
# =============================================================================
class SystemHealthStats(BaseModel):
    """Solo contadores agregados.

    Deliberadamente NO expone `provider`, `key_hint`, `last_check_error` ni URLs de tools: ese
    detalle es de superadmin (D-004) y este endpoint es de backoffice. Si alguien añade aquí
    "qué proveedor falló", abre una fuga de RBAC.
    """

    provider_credentials_total: int
    provider_credentials_active: int
    provider_credentials_failing_check: int
    provider_credentials_never_checked: int

    agent_configs_total: int
    agent_configs_active: int
    has_default_agent_config: bool

    tools_total: int
    tools_active: int
    tool_invocations_in_window: int
    tool_invocation_errors_in_window: int
    tool_error_percent: float | None = Field(
        default=None, description="Null when no tool ran in the window."
    )

    videos_failed: int
    videos_stuck_processing: int = Field(
        description="Videos processing for longer than expected: usually a dead worker."
    )
    documents_failed: int
    documents_stuck_processing: int


# =============================================================================
#  Formación
# =============================================================================
class TrainingStats(BaseModel):
    excludes_demo_users: bool = Field(
        default=True,
        description="Demo accounts are EXCLUDED here. The demo login is shared, so counting "
        "its completions would misrepresent adoption rather than measure it.",
    )

    users_total: int
    users_active: int
    trainees_total: int
    users_logged_in_in_window: int = Field(
        description="Users whose last sign-in falls in the window. Because last_login_at is "
        "monotonic this is exactly the number of distinct users who signed in at least once."
    )

    progress_rows_total: int
    lessons_in_progress: int
    lessons_completed: int
    lessons_completed_in_window: int
    average_watched_percent: float | None = Field(
        default=None,
        description="Averaged over EXISTING progress rows, i.e. over lessons somebody "
        "started -- not over every possible user x lesson pair. Null when there are none.",
    )
    completion_percent: float | None = Field(
        default=None, description="Completed over started. Null when nobody started anything."
    )
    active_users_in_window: int


# =============================================================================
#  Avisos y raíz
# =============================================================================
class PendingAction(BaseModel):
    code: PendingActionCode
    severity: ActionSeverity
    count: int
    message: str = Field(description="Ready to render as-is.")
    resource: str | None = Field(
        default=None, description='Panel route that fixes it, e.g. "agent/knowledge".'
    )


class RecentConversation(BaseModel):
    """Una fila de la tabla de actividad reciente.

    Existe porque una tabla de seis filas se ve completa, mientras que un gráfico de seis
    puntos se ve roto. Con los datos escasos de una demo, esta tarjeta es la que mejor aparenta.
    """

    id: str
    created_at: datetime
    title: str | None = None
    user_name: str
    machine_code: str | None = Field(
        default=None, description="Null when the chat was opened without equipment context."
    )
    machine_name: str | None = None
    message_count: int
    p50_ms: int | None = None
    provider: str | None = None


class StatsOverview(BaseModel):
    generated_at: datetime
    window_days: int
    content: ContentStats
    knowledge: KnowledgeStats
    agent: AgentActivityStats
    health: SystemHealthStats
    training: TrainingStats
    pending_actions: list[PendingAction]
    recent_conversations: list[RecentConversation]
