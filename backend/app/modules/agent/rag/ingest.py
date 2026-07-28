"""Ingesta y vectorización de documentos.

Pipeline: obtener texto -> trocear preservando procedencia -> embeddings por lotes ->
insertar en pgvector.

El troceado conserva el número de página (PDF) o el timestamp (transcripción) en
`source_metadata`. Sin eso, el agente puede citar el documento pero no *dónde*, y en un
manual de 300 páginas eso no sirve de nada al técnico que está frente a la máquina.

Se ejecuta en el worker Celery (cola `ingest`), no en el request: vectorizar un manual de
200 páginas son cientos de llamadas al proveedor de embeddings.
"""

from __future__ import annotations

import io
import logging
import re
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import utcnow
from app.core.config import settings
from app.modules.agent.llm.factory import build_embeddings
from app.modules.agent.models import (
    DocumentSourceType,
    IngestStatus,
    KnowledgeChunk,
    KnowledgeDocument,
)

logger = logging.getLogger(__name__)

# Lotes de embeddings. 64 es un equilibrio entre número de llamadas HTTP y el límite de
# tokens por request de los proveedores.
EMBED_BATCH_SIZE = 64

# `00:12:34` o `[00:12:34]` al inicio de línea en subtítulos/transcripciones.
_TIMESTAMP_RE = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?")

# Encabezado de sección de manual técnico: "4. RESOLUCIÓN DE FALLOS FRECUENTES".
# Se exige mayúscula inicial para no confundirlo con un sub-apartado ("4.1 Revisar el...").
_SECTION_RE = re.compile(r"^\s*(\d+)\.\s+([A-ZÁÉÍÓÚÑÜ][^\n]*)$", re.MULTILINE)


def split_into_sections(text: str) -> list[tuple[str | None, str]]:
    """Parte un manual por sus encabezados de sección numerados.

    Devuelve [(encabezado, cuerpo)]. El texto anterior al primer encabezado (portada,
    título) sale con encabezado `None`.

    Por qué esto y no solo el splitter por caracteres: un manual técnico tiene una
    estructura semántica explícita, y respetarla evita el fallo que se observó en la
    primera versión — un único fragmento que contenía "seguridad del operador", "códigos
    de error" y "mantenimiento preventivo" a la vez. El embedding de ese bloque es un
    promedio de tres temas y sale como primer resultado para cualquier consulta, sin
    discriminar ninguna.
    """
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return [(None, text)]

    sections: list[tuple[str | None, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append((None, preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = f"{match.group(1)}. {match.group(2).strip()}"
        body = text[match.end() : end].strip()
        if body:
            sections.append((heading, body))

    return sections


def _with_context_header(fragment: str, document_title: str, location: str | None) -> str:
    """Antepone al fragmento su procedencia antes de vectorizarlo.

    Técnica de *contextual chunk headers*: el vector del fragmento incorpora el documento y
    la sección de la que sale. Sin el encabezado, un fragmento que dice "E-330
    Sobretemperatura. Dejar enfriar 15 minutos" no contiene la palabra "error" ni el nombre
    del equipo, y una consulta como "qué hago si el equipo se sobrecalienta" lo puntúa peor
    de lo que debería. El encabezado también viaja al LLM, que así puede citar con precisión.
    """
    prefix = f"[{document_title}"
    if location:
        prefix += f" · {location}"
    prefix += "]"
    return f"{prefix}\n{fragment}"


def _splitter() -> RecursiveCharacterTextSplitter:
    # Separadores en orden: párrafo, línea, frase, palabra. Cortar por párrafo primero
    # mantiene juntos los pasos de un procedimiento, que es lo que más se consulta.
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def extract_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """Devuelve [(nº de página, texto)]. Páginas vacías (escaneadas) se descartan.

    Nota: pypdf no hace OCR. Un manual escaneado como imagen produce cero chunks y el
    documento quedará indexado con `chunk_count = 0`; el panel debe mostrar ese aviso.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[tuple[int, str]] = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((number, text))
    return pages


def chunk_pdf(data: bytes, document_title: str) -> list[tuple[str, dict]]:
    """Trocea un PDF por página y, dentro de cada página, por sección."""
    splitter = _splitter()
    chunks: list[tuple[str, dict]] = []
    for page_number, text in extract_pdf_pages(data):
        for heading, body in split_into_sections(text):
            location = f"pág. {page_number}" + (f" · {heading}" if heading else "")
            for piece in splitter.split_text(body):
                metadata = {"page": page_number}
                if heading:
                    metadata["section"] = heading
                chunks.append((_with_context_header(piece, document_title, location), metadata))
    return chunks


def chunk_transcript(text: str, document_title: str) -> list[tuple[str, dict]]:
    """Trocea una transcripción anotando el timestamp del primer marcador del fragmento."""
    splitter = _splitter()
    chunks: list[tuple[str, dict]] = []
    for piece in splitter.split_text(text):
        metadata: dict = {}
        for line in piece.splitlines():
            match = _TIMESTAMP_RE.match(line.strip())
            if match:
                metadata["timestamp"] = match.group(1)
                break
        location = f"min. {metadata['timestamp']}" if "timestamp" in metadata else None
        chunks.append((_with_context_header(piece, document_title, location), metadata))
    return chunks


def chunk_plain_text(text: str, document_title: str) -> list[tuple[str, dict]]:
    """Trocea texto plano respetando los encabezados de sección numerados si los hay."""
    splitter = _splitter()
    chunks: list[tuple[str, dict]] = []
    for heading, body in split_into_sections(text):
        for piece in splitter.split_text(body):
            metadata = {"section": heading} if heading else {}
            chunks.append((_with_context_header(piece, document_title, heading), metadata))
    return chunks


async def ingest_document(
    session: AsyncSession,
    document: KnowledgeDocument,
    *,
    file_bytes: bytes | None = None,
) -> int:
    """Vectoriza un documento y devuelve el número de chunks creados.

    Idempotente: borra los chunks previos del documento antes de insertar. Así reindexar
    un manual corregido no deja fragmentos huérfanos de la versión anterior contaminando
    las respuestas del agente.
    """
    document.status = IngestStatus.processing
    document.error_message = None
    session.add(document)
    await session.commit()

    try:
        if document.source_type is DocumentSourceType.manual_pdf:
            if file_bytes is None:
                raise ValueError("Un documento PDF requiere el contenido del fichero.")
            pieces = chunk_pdf(file_bytes, document.title)
        elif document.source_type is DocumentSourceType.video_transcript:
            pieces = chunk_transcript(document.raw_text or "", document.title)
        else:
            pieces = chunk_plain_text(document.raw_text or "", document.title)

        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
        )

        if not pieces:
            document.status = IngestStatus.indexed
            document.chunk_count = 0
            document.indexed_at = utcnow()
            document.error_message = (
                "No text was extracted. If the PDF is a scan, it needs OCR first."
            )
            session.add(document)
            await session.commit()
            return 0

        embeddings = build_embeddings()
        created = 0

        for start in range(0, len(pieces), EMBED_BATCH_SIZE):
            batch = pieces[start : start + EMBED_BATCH_SIZE]
            vectors = await embeddings.aembed_documents([text for text, _ in batch])

            # `strict=True` no es cosmético: si el proveedor de embeddings devolviera menos
            # vectores que fragmentos enviados, `zip` los emparejaría hasta el más corto y se
            # perderían chunks **en silencio**. El documento quedaría marcado como indexado con
            # parte del manual ausente, y eso se manifiesta mucho después como "el agente no
            # encuentra lo que sí está en el PDF".
            for offset, ((text, metadata), vector) in enumerate(zip(batch, vectors, strict=True)):
                enriched = dict(metadata)
                if document.lesson_id:
                    enriched["lesson_id"] = str(document.lesson_id)

                session.add(
                    KnowledgeChunk(
                        document_id=document.id,
                        machine_model_id=document.machine_model_id,
                        is_global=document.machine_model_id is None,
                        content=text,
                        chunk_index=start + offset,
                        source_metadata=enriched,
                        embedding=vector,
                        embedding_model=settings.EMBEDDING_MODEL,
                        embedding_dim=settings.EMBEDDING_DIM,
                    )
                )
                created += 1

            # Commit por lote: si falla el chunk 800 de 1000, no se pierde el trabajo ya
            # hecho y el reintento reindexa desde cero de forma limpia (es idempotente).
            await session.commit()

        document.status = IngestStatus.indexed
        document.chunk_count = created
        document.indexed_at = utcnow()
        session.add(document)
        await session.commit()
        logger.info("Documento %s indexado con %d chunks", document.id, created)
        return created

    except Exception as exc:
        await session.rollback()
        document.status = IngestStatus.failed
        document.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        session.add(document)
        await session.commit()
        logger.exception("Fallo indexando el documento %s", document.id)
        raise


async def reindex_machine(session: AsyncSession, machine_model_id: uuid.UUID) -> int:
    """Reindexa todos los documentos de una máquina. Usado tras cambiar de modelo de
    embeddings o al corregir el troceado."""
    from sqlalchemy import select

    result = await session.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.machine_model_id == machine_model_id)
    )
    total = 0
    for document in result.scalars():
        if document.source_type is DocumentSourceType.manual_pdf:
            # Los PDF requieren descargar de MinIO; lo orquesta la tarea Celery.
            continue
        total += await ingest_document(session, document)
    return total
