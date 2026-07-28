"""WebSocket del chat: streaming de tokens hacia Flutter.

Dos decisiones que conviene justificar:

1. **Una sesión de BD por mensaje**, no una por conexión. Un socket puede vivir minutos u
   horas mientras el usuario ve un video; mantener una conexión de Postgres abierta todo
   ese tiempo agota el pool con pocos usuarios concurrentes.
2. **El token JWT viaja como query param.** Los WebSockets del navegador no permiten
   cabeceras personalizadas en el handshake. Va sobre TLS y es de vida corta; el riesgo
   conocido es que aparezca en logs de proxies intermedios.

Protocolo (JSON en ambas direcciones):

  cliente -> servidor  {"type":"message","content":"...","machine_model_id":"...",
                        "conversation_id":"...","approved_tools":[]}
  servidor -> cliente  {"type":"start"|"sources"|"token"|"tool_call"|"tool_result"|
                        "confirmation_required"|"done"|"error", "data":{...}}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.database import AsyncSessionFactory
from app.core.deps import get_user_from_token
from app.core.ratelimit import check_rate_limit
from app.modules.agent.schemas import ChatInbound
from app.modules.agent.service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter()

# Códigos de cierre en el rango de aplicación (4000-4999).
WS_UNAUTHORIZED = 4401
WS_RATE_LIMITED = 4429


@router.websocket("/ws")
async def agent_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="Access token JWT."),
) -> None:
    # La autenticación va después de `accept()` a propósito: rechazar antes del handshake
    # da al cliente un error HTTP genérico difícil de distinguir de un fallo de red.
    await websocket.accept()

    async with AsyncSessionFactory() as session:
        user = await get_user_from_token(session, token)

    if user is None:
        await websocket.send_json(
            {
                "type": "error",
                "data": {"message": "Invalid or expired token.", "code": "unauthorized"},
            }
        )
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    logger.info("WS conectado: usuario %s", user.email)

    try:
        while True:
            raw = await websocket.receive_json()

            try:
                inbound = ChatInbound.model_validate(raw)
            except ValidationError as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {"message": "Malformed message.", "detail": exc.errors()[:3]},
                    }
                )
                continue

            if inbound.type == "ping":
                # Keepalive de la app móvil: las redes móviles cierran sockets inactivos.
                await websocket.send_json({"type": "pong", "data": {}})
                continue

            if not inbound.content.strip():
                continue

            allowed, remaining = await check_rate_limit(f"agent:{user.id}")
            if not allowed:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {
                            "message": "You have sent too many messages. Please wait a moment.",
                            "code": "rate_limited",
                        },
                    }
                )
                continue

            # Sesión nueva por turno de conversación.
            async with AsyncSessionFactory() as session:
                service = AgentService(session)
                conversation = await service.get_or_create_conversation(
                    user_id=user.id,
                    conversation_id=inbound.conversation_id,
                    machine_model_id=inbound.machine_model_id,
                    lesson_id=inbound.lesson_id,
                )

                await websocket.send_json(
                    {
                        "type": "conversation",
                        "data": {
                            "conversation_id": str(conversation.id),
                            "rate_limit_remaining": remaining,
                        },
                    }
                )

                try:
                    async for event in service.stream_reply(
                        conversation=conversation,
                        user_message=inbound.content,
                        user_id=user.id,
                        approved_tools=set(inbound.approved_tools),
                    ):
                        await websocket.send_json(event.to_payload())
                except WebSocketDisconnect:
                    # El usuario cerró la app a mitad de la respuesta. No es un error.
                    raise
                except Exception as exc:
                    logger.exception("Error no controlado generando respuesta del agente")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "message": "An error occurred while generating the response.",
                                "code": type(exc).__name__,
                            },
                        }
                    )

    except WebSocketDisconnect:
        logger.info("WS desconectado: usuario %s", user.email)
    except Exception:
        logger.exception("Cierre inesperado del WebSocket del agente")
        await websocket.close(code=1011)
