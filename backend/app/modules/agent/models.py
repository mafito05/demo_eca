"""Modelos del Agent Builder: proveedores, configuración, RAG, tools y conversaciones.

Es el corazón del producto. Cuatro decisiones de diseño guían este esquema:

1. Las credenciales viven cifradas y separadas de la configuración del agente, porque su
   ciclo de vida es distinto: una key se rota sin tocar los agentes que la usan (D-008).
2. El modelo de embeddings queda registrado **por chunk**, no globalmente, para poder
   re-vectorizar por lotes sin perder el corpus (D-005).
3. `machine_model_id` está desnormalizado en `knowledge_chunks` para que el filtro del
   RAG sea un WHERE sobre la misma tabla que el índice vectorial, sin JOIN.
4. Las tools guardan su esquema de parámetros como JSON Schema, que es el formato que
   consume el function calling de todos los proveedores.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, Index, String, Text, UniqueConstraint
from sqlmodel import Field

from app.core.base import TimestampedModel, enum_type
from app.core.config import settings


class LLMProviderKey(StrEnum):
    """Proveedores soportados. DeepSeek y Grok hablan el protocolo de OpenAI, pero se
    modelan como proveedores distintos para que el admin vea nombres reales en el panel
    y para poder fijar su `base_url` y catálogo de modelos por separado."""

    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    grok = "grok"
    deepseek = "deepseek"


class DocumentSourceType(StrEnum):
    manual_pdf = "manual_pdf"
    video_transcript = "video_transcript"
    raw_text = "raw_text"


class IngestStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class ToolAuthType(StrEnum):
    none = "none"
    bearer = "bearer"
    api_key_header = "api_key_header"
    basic = "basic"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


# =============================================================================
#  Credenciales de proveedor
# =============================================================================
class ProviderCredential(TimestampedModel, table=True):
    """API key de un proveedor, cifrada en reposo.

    Se permiten varias por proveedor (`label`) para separar entornos o cuentas de coste,
    pero solo una activa a la vez por proveedor.
    """

    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("provider", "label", name="uq_credential_provider_label"),)

    provider: LLMProviderKey = Field(sa_type=enum_type(LLMProviderKey), index=True, nullable=False)
    label: str = Field(default="default", sa_type=String(64), nullable=False)
    # Ciphertext Fernet. Nunca sale de la API en claro.
    encrypted_api_key: str = Field(sa_type=Text, nullable=False)
    # Últimos 4 caracteres de la key en claro, guardados al crearla. Permite que el panel
    # muestre "••••a1b2" sin descifrar nada para renderizar una lista.
    key_hint: str = Field(default="", sa_type=String(8), nullable=False)
    # Permite apuntar a un gateway propio, Azure OpenAI o un proxy corporativo.
    base_url: str | None = Field(default=None, sa_type=String(512))
    is_active: bool = Field(default=True, index=True, nullable=False)

    # Resultado del último test de conectividad lanzado desde el panel. Sin esto, un
    # error de key solo se descubre cuando un usuario abre el chat en medio de la demo.
    last_checked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    last_check_ok: bool | None = Field(default=None)
    last_check_error: str | None = Field(default=None, sa_type=Text)


# =============================================================================
#  Configuración del agente
# =============================================================================
class AgentConfig(TimestampedModel, table=True):
    """Un "agente" configurable desde el panel.

    `machine_model_id` nulo = agente global (fallback). Con valor = override para esa
    máquina. Así se puede tener un agente general y afinar el de urología sin duplicar
    toda la configuración.
    """

    __tablename__ = "agent_configs"

    name: str = Field(sa_type=String(120), nullable=False)
    description: str | None = Field(default=None, sa_type=Text)

    provider: LLMProviderKey = Field(sa_type=enum_type(LLMProviderKey), nullable=False)
    model_name: str = Field(sa_type=String(120), nullable=False)
    temperature: float = Field(default=0.2, nullable=False)
    max_tokens: int = Field(default=1024, nullable=False)

    # Instrucciones adicionales del admin. Se CONCATENAN al prompt base de seguridad
    # (D-006); no lo sustituyen. El admin no puede desactivar los guardrails clínicos.
    system_prompt_extra: str | None = Field(default=None, sa_type=Text)

    # Preguntas sugeridas que la app muestra en el estado vacío del chat (D-053). Vivían
    # hardcodeadas en el Flutter, lo que obligaba a recompilar la app para cambiar un ejemplo.
    # Lista vacía = la app recibe las preguntas por defecto del backend.
    suggested_questions: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    rag_enabled: bool = Field(default=True, nullable=False)
    rag_top_k: int = Field(default=settings.RAG_TOP_K, nullable=False)
    tools_enabled: bool = Field(default=False, nullable=False)

    machine_model_id: uuid.UUID | None = Field(
        default=None, foreign_key="machine_models.id", index=True
    )
    is_default: bool = Field(default=False, index=True, nullable=False)
    is_active: bool = Field(default=True, index=True, nullable=False)


# =============================================================================
#  RAG
# =============================================================================
class KnowledgeDocument(TimestampedModel, table=True):
    """Documento fuente: manual PDF, transcripción de video o texto pegado a mano.

    `machine_model_id` nulo = corpus global (normativa, procedimientos de la compañía),
    visible para cualquier máquina.
    """

    __tablename__ = "knowledge_documents"

    title: str = Field(sa_type=String(255), nullable=False)
    source_type: DocumentSourceType = Field(sa_type=enum_type(DocumentSourceType), nullable=False)
    machine_model_id: uuid.UUID | None = Field(
        default=None, foreign_key="machine_models.id", index=True
    )
    # Lección de origen si el documento es la transcripción de su video. Permite citar
    # "minuto X de la lección Y" en lugar de solo el nombre del fichero.
    lesson_id: uuid.UUID | None = Field(default=None, foreign_key="lessons.id", index=True)

    object_key: str | None = Field(default=None, sa_type=String(512))
    raw_text: str | None = Field(default=None, sa_type=Text)

    status: IngestStatus = Field(
        default=IngestStatus.pending,
        sa_type=enum_type(IngestStatus, 16),
        index=True,
        nullable=False,
    )
    chunk_count: int = Field(default=0, nullable=False)
    error_message: str | None = Field(default=None, sa_type=Text)
    indexed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class KnowledgeChunk(TimestampedModel, table=True):
    """Fragmento vectorizado.

    La dimensión del vector se fija en el DDL desde `settings.EMBEDDING_DIM`: cambiarla
    exige una migración, y eso es intencionado (D-005). `embedding_model` y
    `embedding_dim` se guardan por fila para poder re-vectorizar incrementalmente.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        # Índice HNSW para búsqueda aproximada por distancia coseno. Se prefiere a IVFFlat
        # porque no requiere entrenar con datos previos: en una demo el corpus crece desde
        # cero y un IVFFlat mal entrenado devuelve resultados pobres.
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: uuid.UUID = Field(foreign_key="knowledge_documents.id", index=True, nullable=False)
    # Desnormalizado desde el documento: el filtro del RAG es el 100% de las queries.
    machine_model_id: uuid.UUID | None = Field(
        default=None, foreign_key="machine_models.id", index=True
    )
    is_global: bool = Field(default=False, index=True, nullable=False)

    content: str = Field(sa_type=Text, nullable=False)
    chunk_index: int = Field(default=0, nullable=False)
    # Página del PDF, timestamp del video, sección... Lo que haga citable el fragmento.
    source_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    embedding: list[float] = Field(sa_column=Column(Vector(settings.EMBEDDING_DIM), nullable=False))
    embedding_model: str = Field(sa_type=String(120), nullable=False)
    embedding_dim: int = Field(default=settings.EMBEDDING_DIM, nullable=False)


# =============================================================================
#  Tools HTTP dinámicas
# =============================================================================
class ToolDefinition(TimestampedModel, table=True):
    """API HTTP externa expuesta al LLM como function call.

    Todos los controles de D-007 se aplican en `tools/security.py` en el momento de la
    invocación, no solo al guardar: la allowlist puede cambiar después del registro.
    """

    __tablename__ = "tool_definitions"

    # Nombre de la función tal como lo ve el LLM. Debe ser un identificador válido:
    # los proveedores rechazan nombres con espacios o acentos.
    name: str = Field(sa_type=String(64), unique=True, index=True, nullable=False)
    # Esta descripción es lo que decide si el LLM usa la tool o no. Es prompt, no docs.
    description: str = Field(sa_type=Text, nullable=False)

    http_method: str = Field(default="GET", sa_type=String(8), nullable=False)
    # Soporta plantillas de path: `https://api.x.com/machines/{serial}/status`
    url_template: str = Field(sa_type=String(1024), nullable=False)

    # JSON Schema de los parámetros. Se convierte en el schema de la function call y en
    # un modelo Pydantic dinámico para validar antes de salir a la red.
    parameters_schema: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    static_headers: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    auth_type: ToolAuthType = Field(
        default=ToolAuthType.none, sa_type=enum_type(ToolAuthType, 24), nullable=False
    )
    # Cifrado con Fernet igual que las API keys de proveedor.
    encrypted_auth_secret: str | None = Field(default=None, sa_type=Text)
    auth_secret_hint: str = Field(default="", sa_type=String(8), nullable=False)
    auth_header_name: str | None = Field(default=None, sa_type=String(64))

    # Si la tool no es idempotente (POST/PUT/DELETE que muta algo), el móvil pide
    # confirmación explícita al usuario antes de ejecutarla. Un LLM no debe poder
    # disparar efectos secundarios por su cuenta.
    requires_confirmation: bool = Field(default=True, nullable=False)
    timeout_seconds: int = Field(default=settings.TOOL_TIMEOUT_SECONDS, nullable=False)

    # Nulo = disponible para todos los agentes; con valor = solo para esa máquina.
    machine_model_id: uuid.UUID | None = Field(
        default=None, foreign_key="machine_models.id", index=True
    )
    is_active: bool = Field(default=False, index=True, nullable=False)


class ToolInvocation(TimestampedModel, table=True):
    """Auditoría de cada ejecución de tool.

    Obligatoria: es la única forma de responder "¿qué hizo el agente en el sistema?".
    """

    __tablename__ = "tool_invocations"

    tool_definition_id: uuid.UUID = Field(
        foreign_key="tool_definitions.id", index=True, nullable=False
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, foreign_key="conversations.id", index=True
    )
    user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)

    arguments: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status_code: int | None = Field(default=None)
    # Truncada a TOOL_MAX_RESPONSE_BYTES.
    response_excerpt: str | None = Field(default=None, sa_type=Text)
    error_message: str | None = Field(default=None, sa_type=Text)
    duration_ms: int | None = Field(default=None)


# =============================================================================
#  Conversaciones
# =============================================================================
class Conversation(TimestampedModel, table=True):
    __tablename__ = "conversations"

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    # Contexto de la máquina desde la que se abrió el chat flotante.
    machine_model_id: uuid.UUID | None = Field(
        default=None, foreign_key="machine_models.id", index=True
    )
    # Contexto más fino: la lección concreta que el usuario está viendo.
    lesson_id: uuid.UUID | None = Field(default=None, foreign_key="lessons.id")
    agent_config_id: uuid.UUID | None = Field(default=None, foreign_key="agent_configs.id")

    title: str | None = Field(default=None, sa_type=String(255))
    is_archived: bool = Field(default=False, nullable=False)


class Message(TimestampedModel, table=True):
    __tablename__ = "messages"

    conversation_id: uuid.UUID = Field(foreign_key="conversations.id", index=True, nullable=False)
    role: MessageRole = Field(sa_type=enum_type(MessageRole, 16), nullable=False)
    content: str = Field(sa_type=Text, nullable=False)

    # Fuentes RAG citadas: [{"document_id": ..., "title": ..., "page": 12, "distance": 0.21}]
    # Se persisten para poder auditar de dónde salió una afirmación del agente.
    sources: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    tool_calls: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    # Observabilidad y coste. Sin esto no hay forma de saber qué cuesta el producto.
    provider: str | None = Field(default=None, sa_type=String(32))
    model_name: str | None = Field(default=None, sa_type=String(120))
    prompt_tokens: int | None = Field(default=None)
    completion_tokens: int | None = Field(default=None)
    latency_ms: int | None = Field(default=None)
