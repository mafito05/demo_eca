"""Rate limiting sencillo con Redis (ventana fija por minuto).

Se aplica al agente porque cada mensaje cuesta dinero real en el proveedor LLM. Sin esto,
un bucle en el cliente puede quemar el presupuesto de la demo en minutos.

Ventana fija y no sliding window a propósito: un INCR + EXPIRE es una operación, sin Lua
ni sorted sets. Permite hasta 2x el límite en el borde entre ventanas, lo cual es
aceptable para proteger coste (no lo sería para proteger contra fuerza bruta de login).
"""

from __future__ import annotations

import logging
import time

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def check_rate_limit(
    identifier: str, *, limit: int | None = None, window: int = 60
) -> tuple[bool, int]:
    """Devuelve (permitido, peticiones_restantes).

    Si Redis no está disponible se permite la petición (fail-open) y se registra: caer el
    chat entero porque el limitador está caído es peor que servir tráfico sin limitar.
    """
    limit = limit or settings.AGENT_RATE_LIMIT_PER_MINUTE
    bucket = int(time.time() // window)
    key = f"ratelimit:{identifier}:{bucket}"

    try:
        redis = get_redis()
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window + 1)
        count, _ = await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rate limiter no disponible, se permite la petición: %s", exc)
        return True, limit

    return int(count) <= limit, max(0, limit - int(count))
