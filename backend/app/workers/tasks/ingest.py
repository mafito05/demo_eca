"""Tarea de vectorización de documentos (cola `ingest`)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import download_bytes
from app.modules.agent.models import DocumentSourceType, KnowledgeDocument
from app.modules.agent.rag.ingest import ingest_document
from app.workers.celery_app import celery_app
from app.workers.runtime import run_with_session

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.ingest.ingest_document_task",
    bind=True,
    max_retries=3,
    # Backoff exponencial con jitter: los proveedores de embeddings devuelven 429 en
    # ráfagas y reintentar todos a la vez empeora el problema.
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def ingest_document_task(self, document_id: str) -> dict:
    """Vectoriza un documento y devuelve el número de chunks creados."""

    async def _work(session: AsyncSession) -> dict:
        document = await session.get(KnowledgeDocument, uuid.UUID(document_id))
        if document is None:
            logger.error("Documento %s no encontrado; nada que indexar.", document_id)
            return {"document_id": document_id, "chunks": 0, "error": "not_found"}

        file_bytes = None
        if document.source_type is DocumentSourceType.manual_pdf:
            if not document.object_key:
                raise ValueError("El documento PDF no tiene `object_key`.")
            file_bytes = download_bytes(settings.MINIO_BUCKET_DOCS, document.object_key)

        chunks = await ingest_document(session, document, file_bytes=file_bytes)
        return {"document_id": document_id, "chunks": chunks}

    return run_with_session(_work)
