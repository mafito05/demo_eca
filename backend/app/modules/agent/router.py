"""Endpoints REST del Agent Builder (panel Angular) y del chat (app Flutter).

Reparto de permisos (D-004):
- Credenciales de proveedor y tools HTTP -> `superadmin`. Son superficie de ataque.
- Configuración de agentes y base de conocimiento -> `admin`. Es contenido.
- Conversaciones -> el usuario dueño de la conversación.
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt, mask
from app.core.deps import CurrentUser, SessionDep, require_backoffice, require_superadmin
from app.modules.agent import prompts, schemas
from app.modules.agent.llm.factory import ProviderNotConfiguredError, build_chat_model
from app.modules.agent.llm.registry import catalog_for_panel
from app.modules.agent.models import (
    AgentConfig,
    Conversation,
    KnowledgeDocument,
    Message,
    ProviderCredential,
    ToolDefinition,
)
from app.modules.agent.rag import retriever
from app.modules.agent.service import AgentService
from app.modules.agent.tools.security import validate_url

router = APIRouter()


# =============================================================================
#  Catálogo de proveedores
# =============================================================================
@router.get(
    "/providers",
    summary="Catalogue of supported LLM providers",
    dependencies=[Depends(require_backoffice)],
)
async def list_providers() -> list[dict]:
    """Alimenta el selector de proveedor/modelo del panel."""
    return catalog_for_panel()


@router.get(
    "/settings",
    response_model=schemas.AgentRuntimeSettings,
    summary="RAG parameters clients need for display",
)
async def runtime_settings(user: CurrentUser) -> schemas.AgentRuntimeSettings:
    """Umbral de distancia y top_k, para que panel y app no los dupliquen (D-053).

    Antes el 0.65 estaba copiado a mano en tres sitios: aquí, el playground de Angular y los
    chips de fuentes de Flutter. Cambiarlo en el `.env` los desincronizaba en silencio.
    """
    return schemas.AgentRuntimeSettings(
        rag_max_distance=settings.RAG_MAX_DISTANCE,
        rag_top_k=settings.RAG_TOP_K,
    )


@router.get(
    "/suggestions",
    response_model=schemas.SuggestedQuestions,
    summary="Example questions for the empty chat state",
)
async def suggested_questions(
    session: SessionDep,
    user: CurrentUser,
    machine_model_id: Annotated[uuid.UUID | None, Query()] = None,
) -> schemas.SuggestedQuestions:
    """Resuelve la configuración igual que el chat: específica de la máquina o la por defecto.

    Así las preguntas que ve el usuario son las del MISMO agente que va a responderle. Si esa
    configuración no define ninguna, se devuelven las por defecto del backend — la app nunca
    recibe una lista vacía.
    """
    service = AgentService(session)
    try:
        config = await service.resolve_config(machine_model_id)
        questions = list(config.suggested_questions or [])
    except ProviderNotConfiguredError:
        # Sin agente configurado el chat no funcionará, pero el estado vacío sí debe pintarse.
        questions = []

    source = "config"
    if not questions:
        source = "default"
        questions = (
            prompts.DEFAULT_EQUIPMENT_QUESTIONS
            if machine_model_id is not None
            else prompts.DEFAULT_GENERAL_QUESTIONS
        )

    return schemas.SuggestedQuestions(
        questions=questions,
        has_machine_context=machine_model_id is not None,
        source=source,
    )


@router.get(
    "/prompt",
    response_model=schemas.BasePromptRead,
    dependencies=[Depends(require_backoffice)],
    summary="The base system prompt, read-only",
)
async def base_prompt() -> schemas.BasePromptRead:
    """Visible, no editable (D-006).

    El panel lo muestra para que el admin sepa exactamente qué reglas lleva el agente antes de
    escribir sus instrucciones adicionales. No hay endpoint de escritura a propósito: los
    guardrails clínicos (no dosis, no consejo de tratamiento) no se desactivan desde una
    pantalla.
    """
    return schemas.BasePromptRead(
        base_prompt=prompts.BASE_SYSTEM_PROMPT,
        machine_context_template=prompts.MACHINE_CONTEXT_TEMPLATE,
        no_context_notice=prompts.NO_CONTEXT_NOTICE,
    )


# =============================================================================
#  Credenciales
# =============================================================================
def _credential_read(credential: ProviderCredential) -> schemas.ProviderCredentialRead:
    return schemas.ProviderCredentialRead(
        id=credential.id,
        provider=credential.provider,
        label=credential.label,
        api_key_masked=mask(credential.key_hint),
        base_url=credential.base_url,
        is_active=credential.is_active,
        last_checked_at=credential.last_checked_at,
        last_check_ok=credential.last_check_ok,
        last_check_error=credential.last_check_error,
    )


@router.get(
    "/credentials",
    response_model=list[schemas.ProviderCredentialRead],
    dependencies=[Depends(require_superadmin)],
)
async def list_credentials(session: SessionDep) -> list[schemas.ProviderCredentialRead]:
    result = await session.execute(select(ProviderCredential).order_by(ProviderCredential.provider))
    return [_credential_read(row) for row in result.scalars()]


@router.post(
    "/credentials",
    response_model=schemas.ProviderCredentialRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
)
async def create_credential(
    payload: schemas.ProviderCredentialCreate, session: SessionDep
) -> schemas.ProviderCredentialRead:
    if payload.is_active:
        # Solo una credencial activa por proveedor: evita ambigüedad sobre qué key se usa.
        existing = await session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider == payload.provider,
                ProviderCredential.is_active.is_(True),
            )
        )
        for row in existing.scalars():
            row.is_active = False
            session.add(row)

    credential = ProviderCredential(
        provider=payload.provider,
        label=payload.label,
        encrypted_api_key=encrypt(payload.api_key),
        key_hint=payload.api_key[-4:],
        base_url=payload.base_url,
        is_active=payload.is_active,
    )
    session.add(credential)
    await session.commit()
    return _credential_read(credential)


@router.patch(
    "/credentials/{credential_id}",
    response_model=schemas.ProviderCredentialRead,
    dependencies=[Depends(require_superadmin)],
)
async def update_credential(
    credential_id: uuid.UUID, payload: schemas.ProviderCredentialUpdate, session: SessionDep
) -> schemas.ProviderCredentialRead:
    credential = await session.get(ProviderCredential, credential_id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found.")

    if payload.api_key:
        credential.encrypted_api_key = encrypt(payload.api_key)
        credential.key_hint = payload.api_key[-4:]
        # La key cambió: el resultado del último test ya no dice nada.
        credential.last_check_ok = None
        credential.last_checked_at = None
    if payload.base_url is not None:
        credential.base_url = payload.base_url
    if payload.is_active is not None:
        credential.is_active = payload.is_active

    session.add(credential)
    await session.commit()
    return _credential_read(credential)


@router.post(
    "/credentials/{credential_id}/test",
    response_model=schemas.CredentialTestResult,
    dependencies=[Depends(require_superadmin)],
)
async def test_credential(
    credential_id: uuid.UUID,
    session: SessionDep,
    model_name: Annotated[
        str | None, Query(description="Model to test the credential with.")
    ] = None,
) -> schemas.CredentialTestResult:
    """Verifica la conectividad con una llamada mínima.

    Existe para que un error de key se descubra en el panel y no en medio de una demo
    frente al cliente.
    """
    from app.core.base import utcnow
    from app.modules.agent.llm.registry import get_spec

    credential = await session.get(ProviderCredential, credential_id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found.")

    spec = get_spec(credential.provider)
    probe = AgentConfig(
        name="__probe__",
        provider=credential.provider,
        model_name=model_name
        or (spec.suggested_models[0] if spec.suggested_models else "gpt-4o-mini"),
        temperature=0.0,
        max_tokens=64,  # algunos proveedores rechazan max_tokens muy bajos
    )

    started = time.perf_counter()
    try:
        model = build_chat_model(probe, credential, streaming=False)
        await model.ainvoke("Responde únicamente: OK")
        result = schemas.CredentialTestResult(
            ok=True,
            message="Connection successful.",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        credential.last_check_ok = True
        credential.last_check_error = None
    except Exception as exc:  # noqa: BLE001
        result = schemas.CredentialTestResult(
            ok=False, message=f"{type(exc).__name__}: {exc}"[:500]
        )
        credential.last_check_ok = False
        credential.last_check_error = result.message

    credential.last_checked_at = utcnow()
    session.add(credential)
    await session.commit()
    return result


# =============================================================================
#  Configuración de agentes
# =============================================================================
@router.get(
    "/configs",
    response_model=list[schemas.AgentConfigRead],
    dependencies=[Depends(require_backoffice)],
)
async def list_agent_configs(session: SessionDep) -> list[AgentConfig]:
    result = await session.execute(select(AgentConfig).order_by(AgentConfig.created_at.desc()))
    return list(result.scalars())


@router.post(
    "/configs",
    response_model=schemas.AgentConfigRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_backoffice)],
)
async def create_agent_config(
    payload: schemas.AgentConfigCreate, session: SessionDep
) -> AgentConfig:
    if payload.is_default:
        await _clear_default(session)

    config = AgentConfig(**payload.model_dump())
    session.add(config)
    await session.commit()
    return config


@router.patch(
    "/configs/{config_id}",
    response_model=schemas.AgentConfigRead,
    dependencies=[Depends(require_backoffice)],
)
async def update_agent_config(
    config_id: uuid.UUID, payload: schemas.AgentConfigUpdate, session: SessionDep
) -> AgentConfig:
    config = await session.get(AgentConfig, config_id)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found.")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default"):
        await _clear_default(session, exclude_id=config_id)

    for key, value in changes.items():
        setattr(config, key, value)
    session.add(config)
    await session.commit()
    return config


async def _clear_default(session: AsyncSession, exclude_id: uuid.UUID | None = None) -> None:
    """Garantiza un único agente por defecto."""
    result = await session.execute(select(AgentConfig).where(AgentConfig.is_default.is_(True)))
    for row in result.scalars():
        if exclude_id is None or row.id != exclude_id:
            row.is_default = False
            session.add(row)


@router.post(
    "/configs/{config_id}/preview-prompt",
    response_model=schemas.PromptPreview,
    dependencies=[Depends(require_backoffice)],
    summary="Compose the exact system prompt the LLM would receive",
)
async def preview_prompt(
    config_id: uuid.UUID, payload: schemas.PromptPreviewRequest, session: SessionDep
) -> schemas.PromptPreview:
    """Usa `build_system_prompt`, el MISMO código del camino de producción — no una copia.

    Es la pieza que faltaba para depurar un agente: hasta ahora el panel solo veía el textarea
    de instrucciones adicionales, sin forma de saber qué recibía de verdad el modelo. El bloque
    de CONTEXTO del RAG se representa con el aviso de "sin contexto": inyectar chunks reales
    exigiría una consulta de ejemplo, y para inspeccionar la recuperación ya existe el
    retrieval-test.
    """
    from app.modules.machines.models import MachineModel

    config = await session.get(AgentConfig, config_id)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration not found.")

    machine = None
    if payload.machine_model_id is not None:
        machine = await session.get(MachineModel, payload.machine_model_id)
        if machine is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.")

    prompt = prompts.build_system_prompt(
        extra_instructions=config.system_prompt_extra,
        machine_name=machine.name if machine else None,
        machine_code=machine.code if machine else None,
        specialty=machine.specialty.value if machine else None,
        rag_context=None,
    )
    return schemas.PromptPreview(
        prompt=prompt,
        includes_machine_context=machine is not None,
        note=(
            "The RAG CONTEXT block is shown as the no-context notice. At runtime it is replaced "
            "by the retrieved excerpts; use the retrieval inspector to see those."
        ),
    )


# =============================================================================
#  Base de conocimiento (RAG)
# =============================================================================
@router.get(
    "/documents",
    response_model=list[schemas.KnowledgeDocumentRead],
    dependencies=[Depends(require_backoffice)],
)
async def list_documents(
    session: SessionDep,
    machine_model_id: uuid.UUID | None = None,
) -> list[KnowledgeDocument]:
    stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    if machine_model_id is not None:
        stmt = stmt.where(KnowledgeDocument.machine_model_id == machine_model_id)
    result = await session.execute(stmt)
    return list(result.scalars())


@router.post(
    "/documents",
    response_model=schemas.KnowledgeDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_backoffice)],
)
async def create_document(
    payload: schemas.KnowledgeDocumentCreate, session: SessionDep
) -> KnowledgeDocument:
    """Registra el documento y encola su vectorización.

    Devuelve 202: la indexación es asíncrona. El panel debe hacer polling de `status`.
    """
    document = KnowledgeDocument(**payload.model_dump())
    session.add(document)
    await session.commit()

    from app.workers.tasks.ingest import ingest_document_task

    ingest_document_task.delay(str(document.id))
    return document


@router.post(
    "/documents/{document_id}/reindex",
    response_model=schemas.KnowledgeDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_backoffice)],
)
async def reindex_document(document_id: uuid.UUID, session: SessionDep) -> KnowledgeDocument:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")

    from app.workers.tasks.ingest import ingest_document_task

    ingest_document_task.delay(str(document.id))
    return document


@router.post(
    "/retrieval-test",
    response_model=list[schemas.RetrievedChunkRead],
    dependencies=[Depends(require_backoffice)],
)
async def retrieval_test(
    payload: schemas.RetrievalTestRequest, session: SessionDep
) -> list[schemas.RetrievedChunkRead]:
    """Depuración del RAG sin gastar tokens del LLM.

    Cuando el agente responde mal, la primera pregunta siempre es "¿qué recuperó?".
    """
    chunks = await retriever.retrieve(
        session,
        payload.query,
        machine_model_id=payload.machine_model_id,
        top_k=payload.top_k,
        # Sin umbral: en depuración interesa ver también los descartados y su distancia.
        max_distance=2.0,
    )
    return [
        schemas.RetrievedChunkRead(
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            citation=chunk.citation_label,
            distance=chunk.distance,
            content=chunk.content,
        )
        for chunk in chunks
    ]


# =============================================================================
#  Tools
# =============================================================================
def _tool_read(tool: ToolDefinition) -> schemas.ToolDefinitionRead:
    return schemas.ToolDefinitionRead(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        http_method=tool.http_method,
        url_template=tool.url_template,
        parameters_schema=tool.parameters_schema,
        auth_type=tool.auth_type,
        auth_secret_masked=mask(tool.auth_secret_hint) if tool.encrypted_auth_secret else None,
        requires_confirmation=tool.requires_confirmation,
        timeout_seconds=tool.timeout_seconds,
        machine_model_id=tool.machine_model_id,
        is_active=tool.is_active,
    )


@router.get(
    "/tools",
    response_model=list[schemas.ToolDefinitionRead],
    dependencies=[Depends(require_superadmin)],
)
async def list_tools(session: SessionDep) -> list[schemas.ToolDefinitionRead]:
    result = await session.execute(select(ToolDefinition).order_by(ToolDefinition.name))
    return [_tool_read(row) for row in result.scalars()]


@router.post(
    "/tools",
    response_model=schemas.ToolDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
)
async def create_tool(
    payload: schemas.ToolDefinitionCreate, session: SessionDep
) -> schemas.ToolDefinitionRead:
    # Validación temprana de la URL para dar feedback inmediato en el panel. La validación
    # vinculante se repite en cada invocación, porque la allowlist puede cambiar (D-007).
    from app.modules.agent.tools.security import ToolSecurityError

    try:
        validate_url(payload.url_template.split("{")[0] or payload.url_template)
    except ToolSecurityError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    data = payload.model_dump(exclude={"auth_secret"})
    tool = ToolDefinition(
        **data,
        encrypted_auth_secret=encrypt(payload.auth_secret) if payload.auth_secret else None,
        auth_secret_hint=payload.auth_secret[-4:] if payload.auth_secret else "",
    )
    session.add(tool)
    await session.commit()
    return _tool_read(tool)


@router.delete(
    "/tools/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_superadmin)],
)
async def delete_tool(tool_id: uuid.UUID, session: SessionDep) -> None:
    tool = await session.get(ToolDefinition, tool_id)
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tool not found.")
    # Desactivar en lugar de borrar: `tool_invocations` mantiene la FK para auditoría.
    tool.is_active = False
    session.add(tool)
    await session.commit()


# =============================================================================
#  Conversaciones (app móvil)
# =============================================================================
@router.post(
    "/conversations", response_model=schemas.ConversationRead, status_code=status.HTTP_201_CREATED
)
async def start_conversation(
    payload: schemas.ConversationStartRequest, session: SessionDep, user: CurrentUser
) -> Conversation:
    service = AgentService(session)
    return await service.get_or_create_conversation(
        user_id=user.id,
        conversation_id=None,
        machine_model_id=payload.machine_model_id,
        lesson_id=payload.lesson_id,
    )


@router.get("/conversations", response_model=list[schemas.ConversationRead])
async def list_conversations(session: SessionDep, user: CurrentUser) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.is_archived.is_(False))
        .order_by(Conversation.created_at.desc())
        .limit(50)
    )
    return list(result.scalars())


@router.get("/conversations/{conversation_id}/messages", response_model=list[schemas.MessageRead])
async def list_messages(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[Message]:
    conversation = await session.get(Conversation, conversation_id)
    # 404 y no 403 si es de otro usuario: no confirmamos que la conversación exista.
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")

    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars())
