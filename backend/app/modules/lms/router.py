"""Endpoints del LMS: autoría (panel), consumo (app) y servido de HLS.

Reparto: la autoría exige `admin`/`superadmin`; el consumo es del usuario autenticado, y el
servidor **revalida el prerrequisito de módulo** en cada acceso a lección. La app pinta el
candado, pero eso es presentación: en una plataforma que emite certificados, el orden de la
capacitación es parte de lo que se certifica.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from minio.error import S3Error
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import (
    CurrentUser,
    SessionDep,
    bearer_scheme,
    get_user_from_token,
    require_backoffice,
)
from app.core.storage import presign_get, presign_put
from app.modules.lms import hls, schemas, service
from app.modules.lms.models import (
    Lesson,
    LessonContentType,
    ProgressStatus,
    TrainingModule,
    UserLessonProgress,
    VideoAsset,
    VideoStatus,
)
from app.modules.machines.models import MachineModel, PublishStatus

router = APIRouter()

# Tipo MIME de las playlists HLS. Servirlas como text/plain hace que algunos reproductores
# se nieguen a interpretarlas.
M3U8_MEDIA_TYPE = "application/vnd.apple.mpegurl"


async def _get_or_404(session: AsyncSession, model, entity_id: uuid.UUID, label: str):
    entity = await session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found.")
    return entity


# =============================================================================
#  Autoría: módulos
# =============================================================================
@router.post(
    "/modules",
    response_model=schemas.TrainingModuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_backoffice)],
)
async def create_module(
    payload: schemas.TrainingModuleCreate, session: SessionDep
) -> TrainingModule:
    await _get_or_404(session, MachineModel, payload.machine_model_id, "Modelo de máquina")

    # `order_index` es único por máquina: se comprueba aquí para devolver un 409 legible en
    # lugar de dejar que estalle la restricción de la base de datos como un 500.
    clash = await session.execute(
        select(TrainingModule).where(
            TrainingModule.machine_model_id == payload.machine_model_id,
            TrainingModule.order_index == payload.order_index,
        )
    )
    if clash.scalars().first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A module already exists at position {payload.order_index} for this machine.",
        )

    module = TrainingModule(**payload.model_dump())
    session.add(module)
    await session.commit()
    return module


@router.get(
    "/modules",
    response_model=list[schemas.TrainingModuleRead],
    dependencies=[Depends(require_backoffice)],
)
async def list_modules(session: SessionDep, machine_model_id: uuid.UUID) -> list[TrainingModule]:
    result = await session.execute(
        select(TrainingModule)
        .where(TrainingModule.machine_model_id == machine_model_id)
        .order_by(TrainingModule.order_index)
    )
    return list(result.scalars())


@router.patch(
    "/modules/{module_id}",
    response_model=schemas.TrainingModuleRead,
    dependencies=[Depends(require_backoffice)],
)
async def update_module(
    module_id: uuid.UUID, payload: schemas.TrainingModuleUpdate, session: SessionDep
) -> TrainingModule:
    module = await _get_or_404(session, TrainingModule, module_id, "Módulo")
    changes = payload.model_dump(exclude_unset=True)

    # La misma comprobación de posición que hace el POST. Sin ella, mover un módulo a un índice
    # ocupado estalla contra la restricción única de la base de datos como un 500 opaco.
    new_index = changes.get("order_index")
    if new_index is not None and new_index != module.order_index:
        clash = await session.execute(
            select(TrainingModule).where(
                TrainingModule.machine_model_id == module.machine_model_id,
                TrainingModule.order_index == new_index,
                TrainingModule.id != module.id,
            )
        )
        if clash.scalars().first():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A module already exists at position {new_index} for this machine.",
            )

    for key, value in changes.items():
        setattr(module, key, value)
    session.add(module)
    await session.commit()
    return module


@router.delete(
    "/modules/{module_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_backoffice)],
    summary="Permanently delete a module and its lessons",
)
async def delete_module(module_id: uuid.UUID, session: SessionDep) -> None:
    """Borrado real, en cascada manual sobre lo que referencia a cada lección.

    Existe además del archivado (`status: archived`) porque en una demo se crea y se deshace
    contenido constantemente, y acumular experimentos fallidos para siempre no aporta. El
    progreso de los usuarios sobre las lecciones borradas se pierde — el panel lo avisa antes.
    """
    module = await _get_or_404(session, TrainingModule, module_id, "Módulo")

    lesson_ids = list(
        (
            await session.execute(select(Lesson.id).where(Lesson.training_module_id == module.id))
        ).scalars()
    )
    if lesson_ids:
        await _detach_lesson_references(session, lesson_ids)
        await session.execute(delete(Lesson).where(Lesson.id.in_(lesson_ids)))

    await session.delete(module)
    await session.commit()


async def _detach_lesson_references(session: AsyncSession, lesson_ids: list[uuid.UUID]) -> None:
    """Desengancha todo lo que apunta a las lecciones antes de borrarlas.

    El orden importa y es deliberado: el progreso se BORRA (sin lección no significa nada),
    pero las conversaciones y los documentos de conocimiento se CONSERVAN con la referencia a
    NULL — una conversación del agente es auditoría y un documento indexado sigue siendo
    conocimiento válido aunque su lección de origen desaparezca.
    """
    # Imports locales: el módulo agent no depende de lms, así que esto no crea un ciclo.
    from app.modules.agent.models import Conversation, KnowledgeDocument

    await session.execute(
        delete(UserLessonProgress).where(UserLessonProgress.lesson_id.in_(lesson_ids))
    )
    await session.execute(
        update(Conversation).where(Conversation.lesson_id.in_(lesson_ids)).values(lesson_id=None)
    )
    await session.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.lesson_id.in_(lesson_ids))
        .values(lesson_id=None)
    )


# =============================================================================
#  Autoría: lecciones
# =============================================================================
@router.post(
    "/lessons",
    response_model=schemas.LessonRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_backoffice)],
)
async def create_lesson(payload: schemas.LessonCreate, session: SessionDep) -> Lesson:
    await _get_or_404(session, TrainingModule, payload.training_module_id, "Módulo")

    # Coherencia entre el tipo de contenido y el campo que lo aporta. Sin esta validación se
    # puede publicar una lección de video sin video, y el fallo aparece en el móvil del médico.
    if payload.content_type is LessonContentType.video and payload.video_asset_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A `video` lesson requires `video_asset_id`.",
        )
    if payload.content_type is LessonContentType.text and not payload.body:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A `text` lesson requires `body`."
        )
    if payload.content_type is LessonContentType.pdf and not payload.document_key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A `pdf` lesson requires `document_key`.",
        )
    if payload.video_asset_id:
        await _get_or_404(session, VideoAsset, payload.video_asset_id, "Video")

    clash = await session.execute(
        select(Lesson).where(
            Lesson.training_module_id == payload.training_module_id,
            Lesson.order_index == payload.order_index,
        )
    )
    if clash.scalars().first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A lesson already exists at position {payload.order_index} in this module.",
        )

    lesson = Lesson(**payload.model_dump())
    session.add(lesson)
    await session.commit()
    return lesson


@router.patch(
    "/lessons/{lesson_id}",
    response_model=schemas.LessonRead,
    dependencies=[Depends(require_backoffice)],
)
async def update_lesson(
    lesson_id: uuid.UUID, payload: schemas.LessonUpdate, session: SessionDep
) -> Lesson:
    lesson = await _get_or_404(session, Lesson, lesson_id, "Lección")
    changes = payload.model_dump(exclude_unset=True)

    new_index = changes.get("order_index")
    if new_index is not None and new_index != lesson.order_index:
        clash = await session.execute(
            select(Lesson).where(
                Lesson.training_module_id == lesson.training_module_id,
                Lesson.order_index == new_index,
                Lesson.id != lesson.id,
            )
        )
        if clash.scalars().first():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A lesson already exists at position {new_index} in this module.",
            )

    for key, value in changes.items():
        setattr(lesson, key, value)

    # La misma coherencia tipo↔contenido que valida el POST, pero sobre el estado RESULTANTE.
    # Un `setattr` ciego permitía dejar una lección de video sin video con un PATCH, y el fallo
    # aparecía después, en el móvil del médico.
    if lesson.content_type is LessonContentType.video and lesson.video_asset_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A `video` lesson requires `video_asset_id`."
        )
    if lesson.content_type is LessonContentType.text and not lesson.body:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A `text` lesson requires `body`."
        )
    if lesson.content_type is LessonContentType.pdf and not lesson.document_key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A `pdf` lesson requires `document_key`."
        )
    if lesson.video_asset_id:
        await _get_or_404(session, VideoAsset, lesson.video_asset_id, "Video")

    session.add(lesson)
    await session.commit()
    return lesson


@router.delete(
    "/lessons/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_backoffice)],
    summary="Permanently delete a lesson",
)
async def delete_lesson(lesson_id: uuid.UUID, session: SessionDep) -> None:
    """El `VideoAsset` NO se borra: el fichero transcodificado puede reutilizarse en otra lección."""
    lesson = await _get_or_404(session, Lesson, lesson_id, "Lección")
    await _detach_lesson_references(session, [lesson.id])
    await session.delete(lesson)
    await session.commit()


# =============================================================================
#  Autoría: árbol completo para el panel
# =============================================================================
@router.get(
    "/machines/{machine_model_id}/authoring",
    response_model=schemas.AuthoringTree,
    dependencies=[Depends(require_backoffice)],
    summary="Full authoring tree: every module and lesson with their editable fields",
)
async def authoring_tree(machine_model_id: uuid.UUID, session: SessionDep) -> schemas.AuthoringTree:
    """Lo que el editor de contenido necesita para EDITAR, no para consumir.

    Existe porque la ruta de consumo (`/machines/{id}/path`) omite deliberadamente `body`,
    `document_key`, `video_asset_id` y los estados de publicación — datos que al trainee no le
    sirven pero sin los cuales un formulario de edición arranca vacío. Devuelve además los
    módulos y lecciones en borrador y archivados, que el path filtra.
    """
    machine = await _get_or_404(session, MachineModel, machine_model_id, "Modelo de máquina")

    modules = list(
        (
            await session.execute(
                select(TrainingModule)
                .where(TrainingModule.machine_model_id == machine.id)
                .order_by(TrainingModule.order_index)
            )
        ).scalars()
    )
    module_ids = [module.id for module in modules]

    lessons_by_module: dict[uuid.UUID, list[Lesson]] = {}
    video_status: dict[uuid.UUID, VideoStatus] = {}
    if module_ids:
        lessons = list(
            (
                await session.execute(
                    select(Lesson)
                    .where(Lesson.training_module_id.in_(module_ids))
                    .order_by(Lesson.order_index)
                )
            ).scalars()
        )
        for lesson in lessons:
            lessons_by_module.setdefault(lesson.training_module_id, []).append(lesson)

        asset_ids = [lesson.video_asset_id for lesson in lessons if lesson.video_asset_id]
        if asset_ids:
            rows = await session.execute(
                select(VideoAsset.id, VideoAsset.status).where(VideoAsset.id.in_(asset_ids))
            )
            video_status = {row.id: row.status for row in rows}

    return schemas.AuthoringTree(
        machine_model_id=machine.id,
        machine_code=machine.code,
        machine_name=machine.name,
        machine_status=machine.status,
        modules=[
            schemas.ModuleAuthoring(
                id=module.id,
                title=module.title,
                description=module.description,
                order_index=module.order_index,
                requires_previous=module.requires_previous,
                status=module.status,
                lessons=[
                    schemas.LessonAuthoring(
                        id=lesson.id,
                        title=lesson.title,
                        content_type=lesson.content_type,
                        order_index=lesson.order_index,
                        video_asset_id=lesson.video_asset_id,
                        video_status=video_status.get(lesson.video_asset_id)
                        if lesson.video_asset_id
                        else None,
                        document_key=lesson.document_key,
                        body=lesson.body,
                        estimated_minutes=lesson.estimated_minutes,
                        status=lesson.status,
                    )
                    for lesson in lessons_by_module.get(module.id, [])
                ],
            )
            for module in modules
        ],
    )


# =============================================================================
#  Pipeline de video
# =============================================================================
@router.post(
    "/videos/upload-url",
    response_model=schemas.VideoUploadTicket,
    dependencies=[Depends(require_backoffice)],
    summary="Direct-upload ticket for MinIO",
)
async def create_upload_url(
    payload: schemas.VideoUploadRequest, session: SessionDep
) -> schemas.VideoUploadTicket:
    """Registra el asset y devuelve una URL prefirmada.

    El fichero NO pasa por FastAPI (D-010): un `.mp4` de varios GB por el API significa
    timeouts, presión de memoria y reintentos que reempiezan desde cero.
    """
    asset = VideoAsset(
        original_filename=payload.filename,
        # La clave se deriva del id del asset, no del nombre original: evita colisiones y
        # elimina la necesidad de sanear un nombre de fichero que viene del navegador.
        source_key="",
        size_bytes=payload.size_bytes,
        status=VideoStatus.uploaded,
    )
    session.add(asset)
    await session.commit()

    suffix = payload.filename.rsplit(".", 1)[-1].lower() if "." in payload.filename else "mp4"
    if not suffix.isalnum() or len(suffix) > 5:
        suffix = "mp4"
    asset.source_key = f"source/{asset.id}.{suffix}"
    session.add(asset)
    await session.commit()

    return schemas.VideoUploadTicket(
        video_asset_id=asset.id,
        upload_url=presign_put(settings.MINIO_BUCKET_VIDEO, asset.source_key),
        object_key=asset.source_key,
        expires_in_seconds=settings.MINIO_PRESIGN_TTL_SECONDS,
    )


@router.post(
    "/videos/{video_asset_id}/process",
    response_model=schemas.VideoAssetRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_backoffice)],
    summary="Queue HLS transcoding",
)
async def process_video(video_asset_id: uuid.UUID, session: SessionDep) -> VideoAsset:
    asset = await _get_or_404(session, VideoAsset, video_asset_id, "Video")

    from app.core.storage import object_exists

    # Se comprueba que el fichero llegó antes de encolar: si la subida del panel falló, el
    # worker gastaría minutos para terminar con un error confuso de ffmpeg.
    if not object_exists(settings.MINIO_BUCKET_VIDEO, asset.source_key):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The source file is not in storage. Did the upload finish?",
        )

    asset.status = VideoStatus.queued
    asset.error_message = None
    session.add(asset)
    await session.commit()

    from app.workers.tasks.video import transcode_video_task

    transcode_video_task.delay(str(asset.id))
    return asset


@router.get(
    "/videos",
    response_model=list[schemas.VideoAssetListItem],
    dependencies=[Depends(require_backoffice)],
    summary="Video library: every uploaded asset and where it is used",
)
async def list_video_assets(session: SessionDep) -> list[schemas.VideoAssetListItem]:
    """La biblioteca que faltaba, y la causa de un bug reportado tal cual.

    El estado del asset recién subido vivía solo en la memoria del navegador: la transcodificación
    tarda ~1 min por minuto de video, y si el admin recargaba o cambiaba de pantalla mientras
    tanto, el video terminaba en `ready` pero quedaba **huérfano e invisible** — "se queda en cola
    y no pasa nada". Con el listado, el panel enseña todos los assets con su estado real y permite
    adjuntar los listos a una lección en cualquier momento.
    """
    assets = list(
        (await session.execute(select(VideoAsset).order_by(VideoAsset.created_at.desc()))).scalars()
    )

    usage: dict[uuid.UUID, list[str]] = {}
    if assets:
        rows = await session.execute(
            select(Lesson.video_asset_id, Lesson.title).where(
                Lesson.video_asset_id.in_([asset.id for asset in assets])
            )
        )
        for row in rows:
            usage.setdefault(row.video_asset_id, []).append(row.title)

    return [
        schemas.VideoAssetListItem(
            id=asset.id,
            original_filename=asset.original_filename,
            status=asset.status,
            duration_seconds=asset.duration_seconds,
            error_message=asset.error_message,
            attempts=asset.attempts,
            created_at=asset.created_at,
            used_by_lessons=usage.get(asset.id, []),
        )
        for asset in assets
    ]


@router.get(
    "/videos/{video_asset_id}",
    response_model=schemas.VideoAssetRead,
    dependencies=[Depends(require_backoffice)],
)
async def get_video_asset(video_asset_id: uuid.UUID, session: SessionDep) -> VideoAsset:
    return await _get_or_404(session, VideoAsset, video_asset_id, "Video")


@router.delete(
    "/videos/{video_asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_backoffice)],
    summary="Delete an UNUSED video asset and its files",
)
async def delete_video_asset(video_asset_id: uuid.UUID, session: SessionDep) -> None:
    """Solo se puede borrar un asset que ninguna lección use: 409 si está en uso.

    Es la protección que hace seguro el botón de la biblioteca — borrar un video referenciado
    dejaría una lección publicada que revienta en el móvil del médico. Para reemplazar el video
    de una lección, primero se cambia el asset en la lección y después se borra el huérfano.

    Los ficheros de MinIO (el mp4 original y el árbol HLS) se borran en el mismo paso, con
    tolerancia a fallos: un objeto ya ausente no debe impedir limpiar la fila.
    """
    asset = await _get_or_404(session, VideoAsset, video_asset_id, "Video")

    used_by = list(
        (
            await session.execute(select(Lesson.title).where(Lesson.video_asset_id == asset.id))
        ).scalars()
    )
    if used_by:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This video is used by: {', '.join(used_by[:3])}. Detach it from the lesson first.",
        )

    from app.core.storage import get_client

    client = get_client()
    try:
        client.remove_object(settings.MINIO_BUCKET_VIDEO, asset.source_key)
        if asset.hls_master_key:
            prefix = asset.hls_master_key.rsplit("/", 1)[0] + "/"
            for obj in client.list_objects(
                settings.MINIO_BUCKET_VIDEO, prefix=prefix, recursive=True
            ):
                client.remove_object(settings.MINIO_BUCKET_VIDEO, obj.object_name)
    except S3Error:
        # Limpiar la fila importa más que un objeto que ya no existía.
        pass

    await session.delete(asset)
    await session.commit()


# =============================================================================
#  Consumo: ruta de aprendizaje
# =============================================================================
@router.get(
    "/machines/{machine_model_id}/path",
    response_model=schemas.LearningPath,
    summary="Training path with the user's progress",
)
async def get_learning_path(
    machine_model_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> schemas.LearningPath:
    """Pantalla principal de la app tras escanear el QR."""
    machine = await _get_or_404(session, MachineModel, machine_model_id, "Modelo de máquina")
    if machine.status != PublishStatus.published and not user.role.is_backoffice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This training is not published yet.")

    return await service.build_learning_path(
        session,
        machine=machine,
        user_id=user.id,
        include_drafts=user.role.is_backoffice,
    )


@router.get("/lessons/{lesson_id}", response_model=schemas.LessonDetail)
async def get_lesson(
    lesson_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> schemas.LessonDetail:
    lesson = await _get_or_404(session, Lesson, lesson_id, "Lección")

    if lesson.status != PublishStatus.published and not user.role.is_backoffice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This lesson is not published yet.")

    if not user.role.is_backoffice and not await service.is_lesson_accessible(
        session, lesson=lesson, user_id=user.id
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You must complete the previous module before opening this lesson.",
        )

    row = await session.execute(
        select(UserLessonProgress).where(
            UserLessonProgress.user_id == user.id,
            UserLessonProgress.lesson_id == lesson.id,
        )
    )
    progress_row = row.scalars().first()
    progress = (
        schemas.LessonProgressRead(
            status=progress_row.status,
            last_position_seconds=progress_row.last_position_seconds,
            watched_percent=progress_row.watched_percent,
            completed_at=progress_row.completed_at,
        )
        if progress_row
        else schemas.LessonProgressRead(
            status=ProgressStatus.not_started,
            last_position_seconds=0.0,
            watched_percent=0.0,
            completed_at=None,
        )
    )

    hls_url: str | None = None
    duration: float | None = None
    if lesson.video_asset_id:
        asset = await session.get(VideoAsset, lesson.video_asset_id)
        if asset and asset.status is VideoStatus.ready:
            duration = asset.duration_seconds
            hls_url = f"{settings.API_V1_PREFIX}/lms/videos/{asset.id}/hls/master.m3u8"

    document_url = (
        presign_get(settings.MINIO_BUCKET_DOCS, lesson.document_key)
        if lesson.document_key
        else None
    )

    return schemas.LessonDetail(
        id=lesson.id,
        title=lesson.title,
        content_type=lesson.content_type,
        body=lesson.body,
        estimated_minutes=lesson.estimated_minutes,
        progress=progress,
        duration_seconds=duration,
        hls_master_url=hls_url,
        document_url=document_url,
    )


@router.put(
    "/lessons/{lesson_id}/progress",
    response_model=schemas.LessonProgressRead,
    summary="Player heartbeat",
)
async def update_progress(
    lesson_id: uuid.UUID,
    payload: schemas.ProgressUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> schemas.LessonProgressRead:
    """Idempotente: el cliente puede llamarlo cada 10 s sin acumular filas.

    Se envía solo la posición. El porcentaje lo calcula el servidor contra la duración real
    del video; si lo enviara el cliente, completar la capacitación sin verla sería un `PUT`.
    """
    lesson = await _get_or_404(session, Lesson, lesson_id, "Lección")

    if not user.role.is_backoffice and not await service.is_lesson_accessible(
        session, lesson=lesson, user_id=user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This lesson is not available to you yet.")

    duration: float | None = None
    if lesson.video_asset_id:
        asset = await session.get(VideoAsset, lesson.video_asset_id)
        duration = asset.duration_seconds if asset else None

    progress = await service.record_progress(
        session,
        user_id=user.id,
        lesson=lesson,
        position_seconds=payload.position_seconds,
        duration_seconds=duration,
    )
    return schemas.LessonProgressRead(
        status=progress.status,
        last_position_seconds=progress.last_position_seconds,
        watched_percent=progress.watched_percent,
        completed_at=progress.completed_at,
    )


# =============================================================================
#  Servido de HLS (D-011)
# =============================================================================
async def _ready_asset(session: AsyncSession, video_asset_id: uuid.UUID) -> VideoAsset:
    asset = await _get_or_404(session, VideoAsset, video_asset_id, "Video")
    if asset.status is not VideoStatus.ready or not asset.hls_master_key:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The video is not ready for playback (status: {asset.status.value}).",
        )
    return asset


@router.get(
    "/videos/{video_asset_id}/hls/master.m3u8",
    response_class=Response,
    summary="Master playlist with signed URIs",
)
async def hls_master(
    video_asset_id: uuid.UUID,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    access_token: Annotated[
        str | None,
        Query(description="Access token JWT, alternative to the Authorization header."),
    ] = None,
) -> Response:
    """Única petición del reproductor que lleva el JWT del usuario.

    Acepta el token por cabecera `Authorization` **o** por query `?access_token=` (D-049). El
    query existe por ExoPlayer: `video_player` aplica `httpHeaders` a TODAS las peticiones del
    data source y las reenvía al seguir redirects, así que una cabecera `Authorization` acababa
    llegando al 307 hacia la URL prefirmada de MinIO — y S3/MinIO rechazan una petición que trae
    firma en la query y `Authorization` a la vez. Con el token en la query de ESTA URL, el
    reproductor no lleva ninguna cabecera y el redirect llega limpio. Mismo patrón que el
    WebSocket del agente (`agent/ws.py`).

    A partir de aquí, las URIs de la playlist llevan un token de reproducción de vida corta
    acotado a este asset, porque los reproductores nativos no garantizan propagar cabeceras a
    las peticiones derivadas del playlist.
    """
    raw_token = access_token or (credentials.credentials if credentials else None)
    user = await get_user_from_token(session, raw_token) if raw_token else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    asset = await _ready_asset(session, video_asset_id)
    token = hls.create_playback_token(asset.id, user.id)
    content = hls.fetch_master(asset.hls_master_key, asset.id, token)
    return Response(
        content=content,
        media_type=M3U8_MEDIA_TYPE,
        # Sin caché: el playlist contiene un token que caduca.
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/videos/{video_asset_id}/hls/{variant}/playlist.m3u8",
    response_class=Response,
    summary="Playlist for a specific quality",
)
async def hls_variant(
    video_asset_id: uuid.UUID,
    variant: str,
    session: SessionDep,
    token: str = Query(..., description="Playback token issued by master.m3u8."),
) -> Response:
    if not hls.verify_playback_token(token, video_asset_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired playback token.")

    asset = await _ready_asset(session, video_asset_id)
    try:
        content = hls.fetch_variant(asset.hls_master_key, asset.id, variant, token)
    except hls.InvalidHLSPath as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except S3Error as exc:
        # Variante que encaja con el patrón pero no existe para este video (p. ej. se pide
        # 1080p y solo se generaron 360p y 720p). Es un 404, no un error del servidor.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Quality '{variant}' does not exist for this video."
        ) from exc

    return Response(
        content=content, media_type=M3U8_MEDIA_TYPE, headers={"Cache-Control": "no-store"}
    )


@router.get(
    "/videos/{video_asset_id}/hls/{variant}/{segment}",
    summary="Video segment (redirect to a presigned URL)",
)
async def hls_segment(
    video_asset_id: uuid.UUID,
    variant: str,
    segment: str,
    session: SessionDep,
    token: str = Query(...),
) -> RedirectResponse:
    """Redirige en lugar de proxificar.

    Los bytes van de MinIO al dispositivo directamente: pasar cientos de megabytes por
    FastAPI es la forma más rápida de tumbarlo con tres usuarios concurrentes. Se usa 307 y
    no 302 para que el método y el rango solicitado se preserven — importante para el
    `Range` que usan los reproductores al buscar dentro del video.
    """
    if not hls.verify_playback_token(token, video_asset_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired playback token.")

    asset = await _ready_asset(session, video_asset_id)
    try:
        url = hls.segment_redirect_url(asset.hls_master_key, variant, segment)
    except hls.InvalidHLSPath as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
