"""Punto de entrada de FastAPI.

El montaje de routers es explícito y no por autodescubrimiento: en una plataforma con
control de acceso por rol, saber de un vistazo qué rutas existen y con qué prefijo es más
valioso que ahorrar diez líneas.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.crypto import SecretDecryptionError
from app.core.database import engine

# Importar el paquete de modelos registra todas las tablas en el metadata de SQLModel.
# Necesario para Alembic y para que las relaciones se resuelvan al arrancar.
from app.models import *  # noqa: F403
from app.modules.agent.llm.factory import ProviderNotConfiguredError
from app.modules.agent.router import router as agent_router
from app.modules.agent.ws import router as agent_ws_router
from app.modules.auth.router import router as auth_router
from app.modules.lms.router import router as lms_router
from app.modules.machines.router import router as machines_router
from app.modules.stats.router import router as stats_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Comprobación temprana: si falta pgvector, el RAG falla al insertar y el error es
    # oscuro. Mejor detectarlo al arrancar.
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            if result.first() is None:
                logger.warning(
                    "La extensión 'vector' no está habilitada en la base de datos. "
                    "Ejecutar: CREATE EXTENSION vector;"
                )
    except Exception as exc:  # noqa: BLE001
        logger.error("No se pudo verificar la base de datos al arrancar: %s", exc)

    if settings.AUTH_BYPASS_ENABLED:
        logger.warning(
            "AUTH_BYPASS_ENABLED=true: el endpoint /auth/demo-login está activo. "
            "Desactivarlo antes de producción."
        )

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
#  Manejadores de errores de configuración
#
#  Sin estos, una API key ausente o una clave de cifrado rotada se manifiestan como un
#  "500 Internal Server Error" opaco. El administrador del panel no tiene forma de saber
#  qué le falta configurar, y en una demo eso se traduce en varios minutos perdidos
#  buscando en los logs del contenedor. Son fallos de configuración, no bugs: merecen un
#  503 con instrucciones.
# -----------------------------------------------------------------------------
@app.exception_handler(ProviderNotConfiguredError)
async def provider_not_configured_handler(
    _: Request, exc: ProviderNotConfiguredError
) -> JSONResponse:
    logger.warning("Configuración de proveedor incompleta: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "code": "provider_not_configured"},
    )


@app.exception_handler(SecretDecryptionError)
async def secret_decryption_handler(_: Request, exc: SecretDecryptionError) -> JSONResponse:
    logger.error("Fallo descifrando un secreto: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": (
                "A stored secret could not be decrypted. If SECRET_ENCRYPTION_KEY changed, the "
                "affected credentials must be registered again."
            ),
            "code": "secret_undecryptable",
        },
    )


@app.get("/health", tags=["infra"], summary="Liveness probe")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "environment": settings.ENVIRONMENT})


@app.get("/health/ready", tags=["infra"], summary="Readiness probe (comprueba Postgres)")
async def readiness() -> JSONResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "database": str(exc)[:200]}, status_code=503)
    return JSONResponse({"status": "ok"})


prefix = settings.API_V1_PREFIX
app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
app.include_router(machines_router, prefix=f"{prefix}/machines", tags=["machines"])
app.include_router(lms_router, prefix=f"{prefix}/lms", tags=["lms"])
app.include_router(agent_router, prefix=f"{prefix}/agent", tags=["agent"])
# El WebSocket cuelga del mismo prefijo: /api/v1/agent/ws
app.include_router(agent_ws_router, prefix=f"{prefix}/agent", tags=["agent"])
app.include_router(stats_router, prefix=f"{prefix}/stats", tags=["stats"])
