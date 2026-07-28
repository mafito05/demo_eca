"""Puente entre las tareas Celery (sincronas) y el código de aplicación (async).

Cada tarea crea su propio engine y su propio event loop, y los destruye al terminar. Es
deliberado: reutilizar el engine global de `app.core.database` desde `asyncio.run()` deja
conexiones asyncpg asociadas a un event loop ya cerrado, y el siguiente uso falla con un
error difícil de diagnosticar ("attached to a different loop").

El coste es una conexión nueva por tarea, irrelevante frente a los segundos o minutos que
dura el trabajo real.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


# Sintaxis de genéricos de PEP 695 (Python 3.12): el parámetro de tipo se declara en la firma
# en lugar de con un `TypeVar` a nivel de módulo.
def run_with_session[T](coro_factory: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Ejecuta una corrutina que necesita una sesión de BD, desde código sincrono."""

    async def _runner() -> T:
        engine = create_async_engine(settings.DATABASE_URL, pool_size=1, max_overflow=0)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())
