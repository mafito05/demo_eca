"""Convierte un `ToolDefinition` de la base de datos en una Tool de LangChain.

Es el puente entre "el admin registró una API en el panel" y "el LLM puede llamarla".
LangChain necesita un esquema de argumentos tipado; nosotros solo tenemos un JSON Schema
guardado en Postgres. La solución es `StructuredTool` con `args_schema` construido al
vuelo desde ese JSON Schema.

Toda invocación se audita en `tool_invocations` (D-007). Los errores se devuelven al LLM
como texto en lugar de lanzarse: si una tool falla, el agente debe poder explicárselo al
usuario, no romper el WebSocket.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import Field as PydanticField
from pydantic import create_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.modules.agent.models import ToolAuthType, ToolDefinition, ToolInvocation
from app.modules.agent.tools.security import ToolSecurityError, truncate_response, validate_url

logger = logging.getLogger(__name__)

# Mapeo JSON Schema -> tipos Python para el modelo Pydantic dinámico.
_JSON_TYPES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def build_args_model(tool: ToolDefinition):
    """Construye un modelo Pydantic desde el JSON Schema de la tool.

    Se valida en nuestro lado antes de salir a la red: el LLM puede alucinar argumentos
    que no existen o tipos incorrectos, y es mejor que eso falle con un mensaje claro que
    llegue a la API externa como un 400 opaco.
    """
    schema = tool.parameters_schema or {}
    properties: dict[str, Any] = schema.get("properties", {})
    required: set[str] = set(schema.get("required", []))

    fields: dict[str, tuple[Any, Any]] = {}
    for name, spec in properties.items():
        python_type = _JSON_TYPES.get(spec.get("type", "string"), str)
        # La descripción viaja al LLM dentro del esquema de la función; sin ella el modelo
        # adivina qué poner en cada campo.
        description = spec.get("description") or None
        if name in required:
            fields[name] = (python_type, PydanticField(..., description=description))
        else:
            fields[name] = (python_type | None, PydanticField(None, description=description))

    if not fields:
        # StructuredTool exige un args_schema; uno vacío es válido para tools sin params.
        return create_model(f"{tool.name.title().replace('_', '')}Args")

    return create_model(f"{tool.name.title().replace('_', '')}Args", **fields)


def _build_headers(tool: ToolDefinition) -> dict[str, str]:
    headers = {"Accept": "application/json", **(tool.static_headers or {})}

    if tool.auth_type is ToolAuthType.none or not tool.encrypted_auth_secret:
        return headers

    secret = decrypt(tool.encrypted_auth_secret)
    if tool.auth_type is ToolAuthType.bearer:
        headers["Authorization"] = f"Bearer {secret}"
    elif tool.auth_type is ToolAuthType.api_key_header:
        headers[tool.auth_header_name or "X-API-Key"] = secret
    elif tool.auth_type is ToolAuthType.basic:
        # El secreto se guarda ya en formato `usuario:contraseña`.
        import base64

        encoded = base64.b64encode(secret.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    return headers


def _render_url(tool: ToolDefinition, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Sustituye los `{placeholders}` del path y devuelve (url, argumentos restantes).

    Lo que no se consume en el path se envía como query string (GET) o como body (resto).
    """
    url = tool.url_template
    remaining = dict(arguments)
    for key, value in arguments.items():
        placeholder = "{" + key + "}"
        if placeholder in url:
            # `quote` evita que un valor con `/` o `?` inyecte segmentos de ruta.
            from urllib.parse import quote

            url = url.replace(placeholder, quote(str(value), safe=""))
            remaining.pop(key, None)
    return url, remaining


async def execute_tool(
    session: AsyncSession,
    tool: ToolDefinition,
    arguments: dict[str, Any],
    *,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> str:
    """Ejecuta la llamada HTTP y devuelve el texto que verá el LLM."""
    started = time.perf_counter()
    invocation = ToolInvocation(
        tool_definition_id=tool.id,
        conversation_id=conversation_id,
        user_id=user_id,
        arguments=arguments,
    )

    try:
        url, remaining = _render_url(tool, arguments)
        validate_url(url)

        method = tool.http_method.upper()
        request_kwargs: dict[str, Any] = {"headers": _build_headers(tool)}
        if method in ("GET", "HEAD", "DELETE"):
            request_kwargs["params"] = remaining
        else:
            request_kwargs["json"] = remaining

        async with httpx.AsyncClient(
            timeout=tool.timeout_seconds,
            # Sin redirecciones: un 302 hacia una IP interna saltaría validate_url.
            follow_redirects=False,
        ) as client:
            response = await client.request(method, url, **request_kwargs)

        invocation.status_code = response.status_code
        body = truncate_response(response.text)
        invocation.response_excerpt = body

        if response.status_code >= 400:
            return (
                f"The API responded with error {response.status_code}. "
                f"Body: {body}\n"
                "Tell the user it failed; do not invent the data they asked for."
            )
        return body

    except ToolSecurityError as exc:
        invocation.error_message = f"BLOQUEADA: {exc}"
        logger.warning("Tool %s bloqueada por política: %s", tool.name, exc)
        return f"The tool could not run due to a security policy: {exc}"

    except httpx.TimeoutException:
        invocation.error_message = "timeout"
        return (
            f"Tool '{tool.name}' did not respond within {tool.timeout_seconds}s. "
            "Tell the user and suggest retrying later."
        )

    except Exception as exc:
        invocation.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        logger.exception("Fallo ejecutando la tool %s", tool.name)
        return f"Error running tool '{tool.name}': {type(exc).__name__}."

    finally:
        invocation.duration_ms = int((time.perf_counter() - started) * 1000)
        session.add(invocation)
        await session.commit()


def to_langchain_tool(
    session: AsyncSession,
    tool: ToolDefinition,
    *,
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> StructuredTool:
    """Envuelve la definición en una tool que LangChain puede bindear al modelo."""

    async def _run(**kwargs: Any) -> str:
        return await execute_tool(
            session,
            tool,
            kwargs,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    description = tool.description
    if tool.requires_confirmation:
        # Refuerzo por prompt. El control real está en el flujo de confirmación del
        # cliente (service.py emite un evento y espera aprobación); esto solo reduce
        # intentos innecesarios.
        description += (
            "\n[This tool has side effects on external systems and requires user "
            "confirmation before it runs.]"
        )

    return StructuredTool(
        name=tool.name,
        description=description,
        args_schema=build_args_model(tool),
        coroutine=_run,
        # No se expone versión sincrona: todo el stack del agente es async.
        func=None,
        handle_tool_error=True,
        metadata={
            "tool_definition_id": str(tool.id),
            "requires_confirmation": tool.requires_confirmation,
        },
    )


def json_schema_preview(tool: ToolDefinition) -> str:
    """Utilidad para el panel: muestra al admin el esquema tal como lo verá el LLM."""
    return json.dumps(
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema,
        },
        indent=2,
        ensure_ascii=False,
    )
