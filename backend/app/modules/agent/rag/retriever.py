"""Recuperación de contexto desde pgvector.

Se consulta pgvector directamente con SQLAlchemy en lugar de usar el `PGVector`
VectorStore de LangChain. Motivos:

- El VectorStore de LangChain gestiona su propio esquema de tablas, que no encaja con el
  modelo relacional del proyecto (chunks ligados a documentos, lecciones y máquinas).
- Necesitamos filtro híbrido (`machine_model_id = X OR is_global`) y umbral de distancia,
  que el wrapper expone de forma limitada.
- El resultado tiene que ser citable, así que necesitamos las columnas de metadatos y el
  título del documento en la misma consulta.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.agent.llm.factory import build_embeddings
from app.modules.agent.models import KnowledgeChunk, KnowledgeDocument


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    distance: float
    metadata: dict

    @property
    def citation_label(self) -> str:
        """Etiqueta legible para citar: "Manual X, pág. 42 · 4. RESOLUCIÓN DE FALLOS".

        Se incluye la sección porque es lo que de verdad usa un técnico que está frente al
        equipo: "está en el manual" no ayuda, "sección 4, código E-204" sí.
        """
        page = self.metadata.get("page")
        section = self.metadata.get("section")
        timestamp = self.metadata.get("timestamp")

        partes = [self.document_title]
        if page is not None:
            partes.append(f"pág. {page}")
        if timestamp:
            partes.append(f"min. {timestamp}")
        if section:
            partes.append(section)
        return " · ".join(partes)


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    machine_model_id: uuid.UUID | None = None,
    top_k: int | None = None,
    max_distance: float | None = None,
    include_global: bool = True,
) -> list[RetrievedChunk]:
    """Búsqueda por similitud coseno con filtro de alcance.

    Devuelve lista vacía si nada supera el umbral. Eso es un resultado válido, no un
    error: el agente responderá "no está en la documentación" en lugar de citar un
    fragmento irrelevante (D-006).
    """
    top_k = top_k or settings.RAG_TOP_K
    max_distance = settings.RAG_MAX_DISTANCE if max_distance is None else max_distance

    embeddings = build_embeddings()
    query_vector = await embeddings.aembed_query(query)

    # `cosine_distance` mapea al operador `<=>` de pgvector, que es el que usa el índice HNSW.
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(
            KnowledgeChunk.id,
            KnowledgeChunk.document_id,
            KnowledgeDocument.title,
            KnowledgeChunk.content,
            KnowledgeChunk.source_metadata,
            distance,
        )
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        # Solo dimensión vigente: si se cambió el modelo de embeddings, los chunks viejos
        # están en otro espacio vectorial y su distancia no significa nada (D-005).
        .where(KnowledgeChunk.embedding_dim == settings.EMBEDDING_DIM)
        .order_by(distance)
        .limit(top_k)
    )

    scope_filters = []
    if machine_model_id is not None:
        scope_filters.append(KnowledgeChunk.machine_model_id == machine_model_id)
    if include_global:
        scope_filters.append(KnowledgeChunk.is_global.is_(True))
    if scope_filters:
        stmt = stmt.where(or_(*scope_filters))

    result = await session.execute(stmt)

    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            content=row.content,
            distance=float(row.distance),
            metadata=row.source_metadata or {},
        )
        for row in result
        if float(row.distance) <= max_distance
    ]


def format_context(chunks: list[RetrievedChunk]) -> tuple[str, list[dict]]:
    """Devuelve (bloque de contexto para el prompt, fuentes serializables para la UI).

    Las fuentes viajan al cliente por WebSocket y se persisten en `Message.sources`, para
    que en el chat se pueda mostrar "según el manual X, pág. 42" con enlace al documento.
    """
    if not chunks:
        return "", []

    blocks: list[str] = []
    sources: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{index}] {chunk.citation_label}\n{chunk.content}")
        sources.append(
            {
                "label": f"[{index}]",
                "document_id": str(chunk.document_id),
                "document_title": chunk.document_title,
                "citation": chunk.citation_label,
                "distance": round(chunk.distance, 4),
                **{
                    k: v
                    for k, v in chunk.metadata.items()
                    if k in ("page", "timestamp", "lesson_id")
                },
            }
        )

    from app.modules.agent.prompts import RAG_CONTEXT_TEMPLATE

    return RAG_CONTEXT_TEMPLATE.format(chunks="\n\n".join(blocks)), sources
