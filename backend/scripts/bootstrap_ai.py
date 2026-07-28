"""Pone en marcha la parte de IA de la demo: credencial de proveedor + vectorización.

    docker compose exec backend python -m scripts.bootstrap_ai

Qué hace:

1. Registra una credencial de proveedor **leyendo la key del entorno**, nunca de un
   argumento de línea de comandos (los argumentos quedan en el historial del shell y en
   `docker inspect`). Por defecto reutiliza `EMBEDDING_API_KEY`, que en el caso de OpenAI es
   la misma cuenta que sirve para chat y para embeddings.
2. Apunta el agente por defecto a ese proveedor si el que tenía configurado no dispone de
   credencial, de modo que el chat funcione sin editar nada a mano.
3. Encola la vectorización de los documentos pendientes en Celery y espera el resultado,
   igual que hará el panel Angular con su polling.

Es una utilidad de desarrollo. En producción las credenciales se registran desde el panel.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from sqlalchemy import select

from app.core.crypto import encrypt
from app.core.database import AsyncSessionFactory, engine

# Registra todas las tablas en el metadata. Sin esto, las claves ajenas hacia tablas de otros
# módulos no resuelven y el commit falla. Ver la nota en app/models.py.
from app.models import *  # noqa: F403
from app.modules.agent.models import (
    AgentConfig,
    IngestStatus,
    KnowledgeDocument,
    LLMProviderKey,
    ProviderCredential,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bootstrap")

# Modelo de chat por defecto al autoconfigurar. Se elige el más barato de cada proveedor:
# esto es una demo, no hay razón para gastar en el modelo grande.
DEFAULT_CHAT_MODEL = {
    LLMProviderKey.openai: "gpt-4o-mini",
    LLMProviderKey.google: "gemini-2.0-flash",
    LLMProviderKey.anthropic: "claude-haiku-4-5-20251001",
    LLMProviderKey.deepseek: "deepseek-chat",
    LLMProviderKey.grok: "grok-3",
}

PROVIDER_ENV_VARS = {
    LLMProviderKey.openai: ("OPENAI_API_KEY", "EMBEDDING_API_KEY"),
    LLMProviderKey.anthropic: ("ANTHROPIC_API_KEY",),
    LLMProviderKey.google: ("GOOGLE_API_KEY", "GEMINI_API_KEY", "EMBEDDING_API_KEY"),
    LLMProviderKey.deepseek: ("DEEPSEEK_API_KEY",),
    LLMProviderKey.grok: ("XAI_API_KEY", "GROK_API_KEY"),
}


def discover_key() -> tuple[LLMProviderKey, str] | None:
    """Busca en el entorno la primera key de proveedor disponible.

    Para OpenAI y Google se acepta `EMBEDDING_API_KEY` como último recurso: es la misma
    cuenta y evita duplicar la variable en la demo.
    """
    for provider, names in PROVIDER_ENV_VARS.items():
        for name in names:
            value = os.environ.get(name, "").strip()
            if value:
                logger.info("Key encontrada en %s -> proveedor '%s'", name, provider.value)
                return provider, value
    return None


async def ensure_credential() -> LLMProviderKey | None:
    found = discover_key()
    if found is None:
        logger.warning(
            "No hay ninguna key de proveedor en el entorno. Variables aceptadas: %s",
            ", ".join(sorted({n for names in PROVIDER_ENV_VARS.values() for n in names})),
        )
        return None

    provider, api_key = found

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider == provider,
                ProviderCredential.label == "bootstrap",
            )
        )
        credential = existing.scalars().first()

        if credential is None:
            # Desactiva otras credenciales del mismo proveedor: solo una activa a la vez.
            others = await session.execute(
                select(ProviderCredential).where(
                    ProviderCredential.provider == provider,
                    ProviderCredential.is_active.is_(True),
                )
            )
            for row in others.scalars():
                row.is_active = False
                session.add(row)

            credential = ProviderCredential(
                provider=provider,
                label="bootstrap",
                encrypted_api_key=encrypt(api_key),
                key_hint=api_key[-4:],
                is_active=True,
            )
            session.add(credential)
            logger.info("Credencial creada para '%s' (••••%s)", provider.value, api_key[-4:])
        else:
            credential.encrypted_api_key = encrypt(api_key)
            credential.key_hint = api_key[-4:]
            credential.is_active = True
            session.add(credential)
            logger.info("Credencial de '%s' actualizada", provider.value)

        # Si el agente por defecto apunta a un proveedor sin credencial, se reapunta a este.
        result = await session.execute(select(AgentConfig).where(AgentConfig.is_default.is_(True)))
        config = result.scalars().first()
        if config is not None and config.provider is not provider:
            has_credential = await session.execute(
                select(ProviderCredential).where(
                    ProviderCredential.provider == config.provider,
                    ProviderCredential.is_active.is_(True),
                )
            )
            if has_credential.scalars().first() is None:
                antes = f"{config.provider.value}/{config.model_name}"
                config.provider = provider
                config.model_name = DEFAULT_CHAT_MODEL[provider]
                session.add(config)
                logger.info(
                    "Agente por defecto reapuntado: %s -> %s/%s (el anterior no tenía credencial)",
                    antes,
                    provider.value,
                    config.model_name,
                )

        await session.commit()

    return provider


async def ingest_pending(timeout_seconds: int = 180, *, force: bool = False) -> bool:
    """Encola los documentos no indexados y espera. Devuelve True si todos quedaron indexados.

    Con `force=True` reindexa también los ya indexados. Es obligatorio tras cambiar el
    troceado o el modelo de embeddings: los chunks antiguos siguen ahí y contaminan las
    respuestas mezclados con los nuevos.
    """
    from app.workers.tasks.ingest import ingest_document_task

    async with AsyncSessionFactory() as session:
        stmt = select(KnowledgeDocument)
        if not force:
            stmt = stmt.where(KnowledgeDocument.status != IngestStatus.indexed)
        result = await session.execute(stmt)
        pending = list(result.scalars())

    if not pending:
        logger.info("No hay documentos pendientes de vectorizar (usar --force para reindexar).")
        return True

    for document in pending:
        ingest_document_task.delay(str(document.id))
        logger.info("Encolado en 'ingest': %s", document.title)

    deadline = time.monotonic() + timeout_seconds
    ids = [document.id for document in pending]

    while time.monotonic() < deadline:
        await asyncio.sleep(3)
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id.in_(ids))
            )
            docs = list(result.scalars())

        estados = ", ".join(f"{d.title[:28]}={d.status.value}({d.chunk_count})" for d in docs)
        logger.info("  %s", estados)

        if all(d.status in (IngestStatus.indexed, IngestStatus.failed) for d in docs):
            for d in docs:
                if d.status is IngestStatus.failed:
                    logger.error("FALLÓ %s: %s", d.title, d.error_message)
            return all(d.status is IngestStatus.indexed for d in docs)

    logger.error("Tiempo de espera agotado. ¿Está el worker de la cola 'ingest' en marcha?")
    return False


async def main() -> int:
    force = "--force" in sys.argv
    provider = await ensure_credential()
    indexed = await ingest_pending(force=force)
    await engine.dispose()

    if provider is None:
        logger.warning("Sin credencial de proveedor: el chat del agente no podrá responder.")
    if not indexed:
        logger.warning("La vectorización no terminó correctamente; el RAG no tendrá contexto.")
    return 0 if (provider is not None and indexed) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
