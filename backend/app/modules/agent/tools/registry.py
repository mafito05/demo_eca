"""Carga las tools aplicables a una conversación."""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import ToolDefinition
from app.modules.agent.tools.http_tool import to_langchain_tool


async def load_tools(
    session: AsyncSession,
    *,
    machine_model_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[list[StructuredTool], dict[str, ToolDefinition]]:
    """Devuelve las tools activas para esta máquina más las globales.

    Se devuelve también el mapa `nombre -> definición` porque `service.py` necesita
    consultar `requires_confirmation` cuando el LLM pide una llamada, y no queremos
    volver a la base de datos en medio del streaming.
    """
    stmt = select(ToolDefinition).where(ToolDefinition.is_active.is_(True))

    scope = [ToolDefinition.machine_model_id.is_(None)]
    if machine_model_id is not None:
        scope.append(ToolDefinition.machine_model_id == machine_model_id)
    stmt = stmt.where(or_(*scope))

    result = await session.execute(stmt)
    definitions = list(result.scalars())

    tools = [
        to_langchain_tool(
            session,
            definition,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        for definition in definitions
    ]
    return tools, {definition.name: definition for definition in definitions}
