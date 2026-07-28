"""Schemas de entrada/salida del Agent Builder.

Regla no negociable: ningún schema de salida expone un secreto. Las credenciales se
devuelven enmascaradas (`crypto.mask`), incluso al superadmin.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.agent.models import (
    DocumentSourceType,
    IngestStatus,
    LLMProviderKey,
    MessageRole,
    ToolAuthType,
)


# =============================================================================
#  Credenciales de proveedor
# =============================================================================
class ProviderCredentialCreate(BaseModel):
    provider: LLMProviderKey
    label: str = Field(default="default", max_length=64)
    api_key: str = Field(min_length=8, description="Encrypted before persisting; never returned.")
    base_url: str | None = None
    is_active: bool = True


class ProviderCredentialUpdate(BaseModel):
    # `api_key` opcional: permite cambiar solo `is_active` o `base_url` sin reenviar la key.
    api_key: str | None = Field(default=None, min_length=8)
    base_url: str | None = None
    is_active: bool | None = None


class ProviderCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: LLMProviderKey
    label: str
    api_key_masked: str
    base_url: str | None
    is_active: bool
    last_checked_at: datetime | None
    last_check_ok: bool | None
    last_check_error: str | None


class CredentialTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None


# =============================================================================
#  Configuración de agente
# =============================================================================
class AgentConfigBase(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None
    provider: LLMProviderKey
    model_name: str = Field(max_length=120)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64, le=32_000)
    system_prompt_extra: str | None = Field(
        default=None,
        description=(
            "Additional instructions. They are APPENDED to the base safety prompt; they do "
            "not replace it, and the clinical guardrails cannot be disabled."
        ),
    )
    rag_enabled: bool = True
    rag_top_k: int = Field(default=5, ge=1, le=20)
    tools_enabled: bool = False
    machine_model_id: uuid.UUID | None = None
    is_default: bool = False
    is_active: bool = True
    suggested_questions: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Example questions the mobile app offers in the empty chat. "
        "Empty list = the app receives the backend defaults.",
    )


class AgentConfigCreate(AgentConfigBase):
    pass


class AgentConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    provider: LLMProviderKey | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=64, le=32_000)
    system_prompt_extra: str | None = None
    rag_enabled: bool | None = None
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    tools_enabled: bool | None = None
    machine_model_id: uuid.UUID | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    suggested_questions: list[str] | None = Field(default=None, max_length=8)


class AgentConfigRead(AgentConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
#  Introspección del agente (D-053)
# =============================================================================
class SuggestedQuestions(BaseModel):
    """Preguntas de ejemplo para el estado vacío del chat de la app."""

    questions: list[str]
    has_machine_context: bool
    source: str = Field(
        description='"config" if they come from the agent configuration, "default" otherwise.'
    )


class AgentRuntimeSettings(BaseModel):
    """Parámetros del RAG que los clientes necesitan para PINTAR, no para decidir.

    Existe porque el umbral de distancia estaba copiado a mano en el panel y en la app: tres
    copias del mismo 0.65 que se desincronizaban en silencio al tocar el `.env`.
    """

    rag_max_distance: float
    rag_top_k: int


class BasePromptRead(BaseModel):
    """El prompt base, visible pero NO editable (D-006).

    Se expone para que el panel pueda mostrarlo: antes ni siquiera se podía ver qué reglas
    llevaba el agente. Sigue sin haber endpoint de escritura a propósito — los guardrails
    clínicos no se desactivan desde una pantalla.
    """

    base_prompt: str
    machine_context_template: str
    no_context_notice: str


class PromptPreviewRequest(BaseModel):
    machine_model_id: uuid.UUID | None = Field(
        default=None, description="Optional equipment to compose the machine context block."
    )


class PromptPreview(BaseModel):
    """El system prompt final que recibiría el LLM con esta configuración."""

    prompt: str
    includes_machine_context: bool
    note: str


# =============================================================================
#  Conocimiento (RAG)
# =============================================================================
class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(max_length=255)
    source_type: DocumentSourceType
    machine_model_id: uuid.UUID | None = Field(
        default=None, description="Null = global document, visible for every machine."
    )
    lesson_id: uuid.UUID | None = None
    raw_text: str | None = Field(
        default=None, description="Required for `raw_text` and `video_transcript`."
    )
    object_key: str | None = Field(default=None, description="Required for `manual_pdf`.")

    @field_validator("raw_text")
    @classmethod
    def _text_required(cls, value: str | None, info: Any) -> str | None:
        source_type = info.data.get("source_type")
        if (
            source_type in (DocumentSourceType.raw_text, DocumentSourceType.video_transcript)
            and not value
        ):
            raise ValueError("`raw_text` es obligatorio para este tipo de documento.")
        return value


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    source_type: DocumentSourceType
    machine_model_id: uuid.UUID | None
    lesson_id: uuid.UUID | None
    status: IngestStatus
    chunk_count: int
    error_message: str | None
    indexed_at: datetime | None
    created_at: datetime


class RetrievalTestRequest(BaseModel):
    """Prueba de recuperación sin gastar tokens del LLM.

    Herramienta de diagnóstico clave para el panel: si el agente responde mal, lo primero
    es ver qué fragmentos recupera y con qué distancia.
    """

    query: str = Field(min_length=3)
    machine_model_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedChunkRead(BaseModel):
    document_id: uuid.UUID
    document_title: str
    citation: str
    distance: float
    content: str


# =============================================================================
#  Tools
# =============================================================================
class ToolDefinitionCreate(BaseModel):
    name: str = Field(
        pattern=r"^[a-z][a-z0-9_]{2,63}$",
        description="snake_case. This is the function name the LLM sees; no spaces or accents.",
    )
    description: str = Field(
        min_length=10,
        description="Decides whether the LLM uses the tool. This is prompt text, not internal docs.",
    )
    http_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url_template: str = Field(max_length=1024)
    parameters_schema: dict = Field(
        default_factory=dict, description="JSON Schema of the parameters."
    )
    static_headers: dict[str, str] = Field(default_factory=dict)
    auth_type: ToolAuthType = ToolAuthType.none
    auth_secret: str | None = Field(default=None, description="Encrypted before persisting.")
    auth_header_name: str | None = None
    requires_confirmation: bool = True
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    machine_model_id: uuid.UUID | None = None
    is_active: bool = False


class ToolDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    http_method: str
    url_template: str
    parameters_schema: dict
    auth_type: ToolAuthType
    auth_secret_masked: str | None = None
    requires_confirmation: bool
    timeout_seconds: int
    machine_model_id: uuid.UUID | None
    is_active: bool


# =============================================================================
#  Conversaciones y chat
# =============================================================================
class ConversationStartRequest(BaseModel):
    machine_model_id: uuid.UUID | None = None
    lesson_id: uuid.UUID | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_model_id: uuid.UUID | None
    lesson_id: uuid.UUID | None
    title: str | None
    created_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    sources: list[dict]
    created_at: datetime


class ChatInbound(BaseModel):
    """Mensaje que envía el cliente por WebSocket."""

    type: Literal["message", "ping"] = "message"
    content: str = Field(default="", max_length=4000)
    conversation_id: uuid.UUID | None = None
    machine_model_id: uuid.UUID | None = None
    lesson_id: uuid.UUID | None = None
    # Tools que el usuario acaba de autorizar tras un evento `confirmation_required`.
    approved_tools: list[str] = Field(default_factory=list)
