"""Orquestación del agente: RAG + multi-LLM + function calling + streaming.

Decisión de diseño central: **el bucle de tool calling es explícito**, no se delega a
`create_react_agent` de LangGraph. Motivos:

- Necesitamos emitir eventos granulares por WebSocket (token, fuentes, llamada a tool,
  resultado) y el agente prefabricado no expone ese detalle de forma estable.
- Necesitamos poder **detenernos** antes de ejecutar una tool que requiere confirmación
  del usuario (D-007). Eso es una interrupción en mitad del razonamiento, y con el bucle
  propio es trivial.
- Una dependencia menos y un flujo que se puede leer de arriba abajo en una revisión.

El servicio no conoce WebSockets: produce un `AsyncIterator` de eventos. Así el mismo
código sirve a WS, a SSE o a un test sin transporte.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.agent.llm.factory import ProviderNotConfiguredError, build_chat_model
from app.modules.agent.models import (
    AgentConfig,
    Conversation,
    LLMProviderKey,
    Message,
    MessageRole,
    ProviderCredential,
)
from app.modules.agent.prompts import build_system_prompt
from app.modules.agent.rag import retriever
from app.modules.agent.tools.http_tool import execute_tool
from app.modules.agent.tools.registry import load_tools
from app.modules.machines.models import MachineModel

logger = logging.getLogger(__name__)

EventType = Literal[
    "start",
    "sources",
    "token",
    "tool_call",
    "tool_result",
    "confirmation_required",
    "done",
    "error",
]


@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -------------------------------------------------------------------------
    #  Resolución de configuración
    # -------------------------------------------------------------------------
    async def resolve_config(self, machine_model_id: uuid.UUID | None) -> AgentConfig:
        """Agente específico de la máquina si existe; si no, el agente por defecto.

        Permite afinar el asistente de un equipo concreto (prompt, modelo, top_k) sin
        duplicar la configuración global.
        """
        if machine_model_id is not None:
            specific = await self.session.execute(
                select(AgentConfig).where(
                    AgentConfig.machine_model_id == machine_model_id,
                    AgentConfig.is_active.is_(True),
                )
            )
            config = specific.scalars().first()
            if config:
                return config

        default = await self.session.execute(
            select(AgentConfig).where(
                AgentConfig.is_default.is_(True), AgentConfig.is_active.is_(True)
            )
        )
        config = default.scalars().first()
        if config is None:
            raise ProviderNotConfiguredError(
                "No agent is configured. A superadmin must create a default AgentConfig "
                "in the admin panel."
            )
        return config

    async def get_credential(self, provider: LLMProviderKey) -> ProviderCredential:
        result = await self.session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider == provider,
                ProviderCredential.is_active.is_(True),
            )
        )
        credential = result.scalars().first()
        if credential is None:
            raise ProviderNotConfiguredError(
                f"No active credential for provider '{provider.value}'."
            )
        return credential

    # -------------------------------------------------------------------------
    #  Historial
    # -------------------------------------------------------------------------
    async def load_history(self, conversation_id: uuid.UUID) -> list[BaseMessage]:
        """Últimos N mensajes en orden cronológico.

        Se recorta por número de mensajes y no por tokens: es una aproximación barata y
        suficiente aquí. Con conversaciones largas conviene sustituirlo por un contador de
        tokens real o por resumen incremental.
        """
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(settings.AGENT_MAX_HISTORY_MESSAGES)
        )
        rows = list(result.scalars())[::-1]

        history: list[BaseMessage] = []
        for row in rows:
            if row.role is MessageRole.user:
                history.append(HumanMessage(content=row.content))
            elif row.role is MessageRole.assistant:
                history.append(AIMessage(content=row.content))
            # Los mensajes de tool no se rehidratan: sin su AIMessage con `tool_calls`
            # correspondiente, algunos proveedores rechazan el historial por inconsistente.
        return history

    async def _machine_context(self, machine_model_id: uuid.UUID | None) -> MachineModel | None:
        if machine_model_id is None:
            return None
        return await self.session.get(MachineModel, machine_model_id)

    # -------------------------------------------------------------------------
    #  Bucle principal
    # -------------------------------------------------------------------------
    async def stream_reply(
        self,
        *,
        conversation: Conversation,
        user_message: str,
        user_id: uuid.UUID,
        approved_tools: set[str] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Genera la respuesta del agente como flujo de eventos.

        `approved_tools` contiene los nombres de tools que el usuario ya autorizó en este
        turno. Las tools con `requires_confirmation=True` que no estén ahí detienen el
        turno con un evento `confirmation_required`; el cliente vuelve a llamar incluyendo
        la autorización.
        """
        approved_tools = approved_tools or set()
        started = time.perf_counter()

        try:
            config = await self.resolve_config(conversation.machine_model_id)
            credential = await self.get_credential(config.provider)
            model = build_chat_model(config, credential, streaming=True)
        except ProviderNotConfiguredError as exc:
            yield AgentEvent("error", {"message": str(exc), "code": "provider_not_configured"})
            return

        machine = await self._machine_context(conversation.machine_model_id)

        yield AgentEvent(
            "start",
            {
                "provider": config.provider.value,
                "model": config.model_name,
                "rag_enabled": config.rag_enabled,
                "machine": machine.name if machine else None,
            },
        )

        # --- RAG -------------------------------------------------------------
        rag_context, sources = "", []
        if config.rag_enabled:
            try:
                chunks = await retriever.retrieve(
                    self.session,
                    user_message,
                    machine_model_id=conversation.machine_model_id,
                    top_k=config.rag_top_k,
                )
                rag_context, sources = retriever.format_context(chunks)
                yield AgentEvent("sources", {"sources": sources})
            except Exception as exc:  # noqa: BLE001
                # Un fallo de embeddings no debe dejar al usuario sin respuesta: se degrada
                # a modo sin contexto y el prompt le dice al modelo que no tiene el manual.
                logger.warning("RAG no disponible, se continúa sin contexto: %s", exc)
                yield AgentEvent("sources", {"sources": [], "degraded": True})

        system_prompt = build_system_prompt(
            extra_instructions=config.system_prompt_extra,
            machine_name=machine.name if machine else None,
            machine_code=machine.code if machine else None,
            specialty=machine.specialty.value if machine else None,
            rag_context=rag_context or None,
        )

        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(await self.load_history(conversation.id))
        messages.append(HumanMessage(content=user_message))

        await self._persist(conversation.id, MessageRole.user, user_message)

        # --- Tools -----------------------------------------------------------
        tool_definitions: dict = {}
        if config.tools_enabled:
            langchain_tools, tool_definitions = await load_tools(
                self.session,
                machine_model_id=conversation.machine_model_id,
                conversation_id=conversation.id,
                user_id=user_id,
            )
            if langchain_tools:
                model = model.bind_tools(langchain_tools)

        # --- Bucle de razonamiento ------------------------------------------
        final_text = ""
        tool_calls_log: list[dict] = []
        usage: dict[str, Any] = {}

        for _ in range(settings.AGENT_MAX_TOOL_ITERATIONS):
            accumulated: AIMessageChunk | None = None
            try:
                async for chunk in model.astream(messages):
                    # Acumular los chunks reconstruye el mensaje completo, incluidos los
                    # argumentos de tool que llegan troceados.
                    accumulated = chunk if accumulated is None else accumulated + chunk
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        final_text += text
                        yield AgentEvent("token", {"text": text})
            except Exception as exc:
                logger.exception("Error en el streaming del proveedor %s", config.provider)
                yield AgentEvent(
                    "error",
                    {
                        "message": f"The provider returned an error: {type(exc).__name__}",
                        "code": "provider_error",
                    },
                )
                return

            if accumulated is None:
                break

            if getattr(accumulated, "usage_metadata", None):
                usage = accumulated.usage_metadata or {}

            requested = getattr(accumulated, "tool_calls", None) or []
            if not requested:
                break

            messages.append(accumulated)

            for call in requested:
                name = call.get("name", "")
                args = call.get("args", {}) or {}
                definition = tool_definitions.get(name)

                if definition is None:
                    messages.append(
                        ToolMessage(
                            content=f"Tool '{name}' does not exist or is disabled.",
                            tool_call_id=call.get("id", ""),
                        )
                    )
                    continue

                if definition.requires_confirmation and name not in approved_tools:
                    # Se corta el turno. El cliente muestra el diálogo de confirmación y
                    # reenvía la petición con la tool autorizada.
                    yield AgentEvent(
                        "confirmation_required",
                        {
                            "tool_name": name,
                            "tool_description": definition.description,
                            "arguments": args,
                            "partial_text": final_text,
                        },
                    )
                    return

                yield AgentEvent("tool_call", {"tool_name": name, "arguments": args})
                output = await execute_tool(
                    self.session,
                    definition,
                    args,
                    conversation_id=conversation.id,
                    user_id=user_id,
                )
                tool_calls_log.append({"name": name, "arguments": args})
                yield AgentEvent("tool_result", {"tool_name": name, "output": output[:2000]})
                messages.append(ToolMessage(content=output, tool_call_id=call.get("id", "")))
        else:
            # Se agotaron las iteraciones sin respuesta final: se avisa en lugar de
            # devolver un texto vacío que parecería un cuelgue.
            logger.warning(
                "Se alcanzó AGENT_MAX_TOOL_ITERATIONS en la conversación %s", conversation.id
            )
            if not final_text:
                final_text = (
                    "I could not complete the request: the assistant chained too many tool "
                    "calls. Please rephrase the question."
                )
                yield AgentEvent("token", {"text": final_text})

        latency_ms = int((time.perf_counter() - started) * 1000)
        await self._persist(
            conversation.id,
            MessageRole.assistant,
            final_text,
            sources=sources,
            tool_calls=tool_calls_log,
            provider=config.provider.value,
            model_name=config.model_name,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            latency_ms=latency_ms,
        )

        yield AgentEvent(
            "done",
            {
                "latency_ms": latency_ms,
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
                "sources": sources,
            },
        )

    # -------------------------------------------------------------------------
    async def _persist(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
        **extra: Any,
    ) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content, **extra)
        self.session.add(message)
        await self.session.commit()
        return message

    async def get_or_create_conversation(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        machine_model_id: uuid.UUID | None,
        lesson_id: uuid.UUID | None = None,
    ) -> Conversation:
        if conversation_id is not None:
            conversation = await self.session.get(Conversation, conversation_id)
            # Comprobación de propiedad: un ID de conversación no debe dar acceso al
            # historial de otro usuario.
            if conversation is not None and conversation.user_id == user_id:
                return conversation

        conversation = Conversation(
            user_id=user_id,
            machine_model_id=machine_model_id,
            lesson_id=lesson_id,
        )
        self.session.add(conversation)
        await self.session.commit()
        return conversation
