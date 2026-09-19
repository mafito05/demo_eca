"""Endpoints de máquinas: catálogo, QR y resolución del deep link."""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from minio.error import S3Error
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import settings
from app.core.deps import CurrentUser, SessionDep, require_backoffice
from app.modules.machines import images as image_service
from app.modules.machines import qr_service, schemas
from app.modules.machines.models import (
    MachineImage,
    MachineImageRole,
    MachineModel,
    PublishStatus,
    Specialty,
)

router = APIRouter()


class MachineCreate(BaseModel):
    code: str = Field(max_length=64, description="Internal company code, e.g. URO-LITHO-3000.")
    name: str = Field(max_length=200)
    manufacturer: str | None = None
    specialty: Specialty = Specialty.otro
    description: str | None = None
    status: PublishStatus = PublishStatus.draft


class MachineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    manufacturer: str | None
    specialty: Specialty
    description: str | None
    status: PublishStatus
    qr_token: str

    lessons_count: int = Field(
        default=0, description="Published lessons available for this equipment."
    )
    completed_lessons: int = Field(
        default=0, description="Lessons the requesting user has completed."
    )
    progress_percent: float = Field(
        default=0.0,
        description="Completion for the requesting user, 0-100. Zero here means "
        "'not started', which is a true statement, so it is not nullable.",
    )

    # Ambos con default: `MachineRead` se construye con `**machine.model_dump()` en varios
    # sitios, y `model_dump()` de la entidad no incluye las imágenes (viven en otra tabla).
    cover_image_url: str | None = Field(
        default=None, description="Public URL of the cover image, or null if none is set."
    )
    images: list[schemas.MachineImageRead] = Field(
        default_factory=list, description="Gallery, ordered. Includes the cover."
    )


class MachineUpdate(BaseModel):
    """Todos opcionales: el panel manda solo lo que cambió.

    `status` es el campo que importa: sin este PATCH, una máquina creada desde el panel nacía en
    `draft` y no había forma de publicarla jamás — su capacitación era invisible para la app.
    El `qr_token` NO es editable a propósito: hay códigos impresos pegados a máquinas físicas.
    """

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = None
    specialty: Specialty | None = None
    description: str | None = None
    status: PublishStatus | None = None


class MachineResolved(BaseModel):
    """Respuesta del escaneo del QR.

    Devuelve el `machine_model_id` explícitamente: es el identificador con el que la app
    trabaja a partir de aquí. El día que el QR apunte a una unidad física en lugar de a un
    modelo (D-002), este contrato no cambia.
    """

    machine_model_id: uuid.UUID
    code: str
    name: str
    specialty: Specialty
    description: str | None
    modules_count: int

    # Lo consume la cabecera del equipo en la app: hasta ahora se pintaba un degradado por
    # especialidad precisamente porque no había fotografía que enseñar.
    cover_image_url: str | None = None
    images: list[schemas.MachineImageRead] = Field(default_factory=list)


@router.post(
    "",
    response_model=MachineRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_backoffice)],
)
async def create_machine(payload: MachineCreate, session: SessionDep) -> MachineModel:
    """Registra una máquina. El `qr_token` se genera aquí, no se pide al cliente."""
    existing = await session.execute(select(MachineModel).where(MachineModel.code == payload.code))
    if existing.scalars().first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A machine with code {payload.code} already exists."
        )

    machine = MachineModel(**payload.model_dump())
    session.add(machine)
    await session.commit()
    return machine


@router.get("", response_model=list[MachineRead])
async def list_machines(session: SessionDep, user: CurrentUser) -> list[MachineRead]:
    """Catálogo con el progreso del usuario que pregunta.

    El progreso y las imágenes vienen aquí, agregados en **tres consultas fijas**, y no en una
    llamada por máquina: la app pinta el porcentaje y la miniatura en cada tarjeta del catálogo,
    así que resolverlo con `/lms/machines/{id}/path` sería un N+1 que crece con el catálogo.
    """
    from app.modules.lms.models import Lesson, ProgressStatus, TrainingModule, UserLessonProgress

    stmt = select(MachineModel).order_by(MachineModel.name)
    # El trainee solo ve catálogo publicado; el backoffice ve también borradores.
    if not user.role.is_backoffice:
        stmt = stmt.where(MachineModel.status == PublishStatus.published)
    machines = list((await session.execute(stmt)).scalars())

    published_lessons = (
        select(
            TrainingModule.machine_model_id.label("machine_id"),
            func.count(Lesson.id).label("total"),
        )
        .join(Lesson, Lesson.training_module_id == TrainingModule.id)
        .where(
            TrainingModule.status == PublishStatus.published,
            Lesson.status == PublishStatus.published,
        )
        .group_by(TrainingModule.machine_model_id)
    )
    totals = {row.machine_id: row.total for row in await session.execute(published_lessons)}

    completed_lessons = (
        select(
            TrainingModule.machine_model_id.label("machine_id"),
            func.count(UserLessonProgress.id).label("done"),
        )
        .select_from(UserLessonProgress)
        .join(Lesson, Lesson.id == UserLessonProgress.lesson_id)
        .join(TrainingModule, TrainingModule.id == Lesson.training_module_id)
        .where(
            UserLessonProgress.user_id == user.id,
            UserLessonProgress.status == ProgressStatus.completed,
            TrainingModule.status == PublishStatus.published,
            Lesson.status == PublishStatus.published,
        )
        .group_by(TrainingModule.machine_model_id)
    )
    done = {row.machine_id: row.done for row in await session.execute(completed_lessons)}

    by_machine = await image_service.load_for_machines(session, [m.id for m in machines])

    return [
        MachineRead(
            **machine.model_dump(),
            lessons_count=totals.get(machine.id, 0),
            completed_lessons=done.get(machine.id, 0),
            progress_percent=(
                round(done.get(machine.id, 0) / totals[machine.id] * 100, 1)
                if totals.get(machine.id)
                else 0.0
            ),
            cover_image_url=image_service.cover_url(by_machine.get(machine.id, [])),
            images=image_service.to_reads(by_machine.get(machine.id, [])),
        )
        for machine in machines
    ]


@router.get(
    "/resolve/{qr_token}",
    response_model=MachineResolved,
    summary="Resolve a scanned QR code",
)
async def resolve_qr(qr_token: str, session: SessionDep, user: CurrentUser) -> MachineResolved:
    """Punto de entrada del flujo completo: QR -> ruta de capacitación.

    Único lugar del sistema que traduce un token de QR a una entidad de dominio. Ver D-002.
    """
    from app.modules.lms.models import TrainingModule

    result = await session.execute(select(MachineModel).where(MachineModel.qr_token == qr_token))
    machine = result.scalars().first()

    if machine is None or (
        machine.status != PublishStatus.published and not user.role.is_backoffice
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "QR code not recognised, or its training is not published yet.",
        )

    modules = await session.execute(
        select(TrainingModule).where(TrainingModule.machine_model_id == machine.id)
    )

    gallery = (await image_service.load_for_machines(session, [machine.id])).get(machine.id, [])

    return MachineResolved(
        machine_model_id=machine.id,
        code=machine.code,
        name=machine.name,
        specialty=machine.specialty,
        description=machine.description,
        modules_count=len(list(modules.scalars())),
        cover_image_url=image_service.cover_url(gallery),
        images=image_service.to_reads(gallery),
    )


@router.patch(
    "/{machine_id}",
    response_model=MachineRead,
    dependencies=[Depends(require_backoffice)],
    summary="Edit a machine, including publishing it",
)
async def update_machine(
    machine_id: uuid.UUID, payload: MachineUpdate, session: SessionDep
) -> MachineRead:
    machine = await _get_machine(session, machine_id)
    changes = payload.model_dump(exclude_unset=True)

    new_code = changes.get("code")
    if new_code and new_code != machine.code:
        existing = await session.execute(
            select(MachineModel).where(MachineModel.code == new_code, MachineModel.id != machine.id)
        )
        if existing.scalars().first():
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A machine with code {new_code} already exists."
            )

    for key, value in changes.items():
        setattr(machine, key, value)
    session.add(machine)
    await session.commit()

    # Misma forma que devuelve el listado, con el progreso a cero: quien edita es backoffice y
    # el dato de progreso es del usuario que consulta, no de la máquina.
    gallery = (await image_service.load_for_machines(session, [machine.id])).get(machine.id, [])
    return MachineRead(
        **machine.model_dump(),
        cover_image_url=image_service.cover_url(gallery),
        images=image_service.to_reads(gallery),
    )


async def _get_machine(session: AsyncSession, machine_id: uuid.UUID) -> MachineModel:
    machine = await session.get(MachineModel, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.")
    return machine


# =============================================================================
#  Imágenes de producto (D-058)
# =============================================================================
async def _get_image(
    session: AsyncSession, machine_id: uuid.UUID, image_id: uuid.UUID
) -> MachineImage:
    """Carga la imagen comprobando que pertenece a esa máquina.

    La comprobación de pertenencia no es ceremonia: sin ella, `/machines/A/images/{id_de_B}`
    dejaría borrar o repromocionar imágenes de otra máquina conociendo solo su id.
    """
    image = await session.get(MachineImage, image_id)
    if image is None or image.machine_model_id != machine_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found for this machine.")
    return image


async def _demote_other_covers(
    session: AsyncSession, machine_id: uuid.UUID, keep_id: uuid.UUID
) -> None:
    """Baja a galería cualquier otra portada. Va en la MISMA transacción que la promoción, o el
    índice único parcial `uq_machine_cover` rechazaría el commit."""
    others = (
        (
            await session.execute(
                select(MachineImage).where(
                    MachineImage.machine_model_id == machine_id,
                    MachineImage.role == MachineImageRole.cover,
                    MachineImage.id != keep_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for other in others:
        other.role = MachineImageRole.gallery
        session.add(other)


@router.post(
    "/{machine_id}/images/upload-url",
    response_model=schemas.MachineImageUploadTicket,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_backoffice)],
    summary="Presigned URL to upload a product image",
)
async def create_image_upload_url(
    machine_id: uuid.UUID, payload: schemas.MachineImageUploadRequest, session: SessionDep
) -> schemas.MachineImageUploadTicket:
    """Primera de las dos fases, calcada del flujo de video (D-010).

    Los bytes van del navegador a MinIO sin pasar por aquí, así que lo que se valida en este
    punto es solo lo que el cliente *declara*. La comprobación de verdad está en `/confirm`.
    """
    machine = await _get_machine(session, machine_id)

    content_type = image_service.normalise_content_type(payload.content_type)
    if not image_service.is_allowed_content_type(content_type):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported image type '{payload.content_type}'. "
            f"Allowed: {', '.join(sorted(image_service.ALLOWED_IMAGE_CONTENT_TYPES))}.",
        )

    if payload.size_bytes and payload.size_bytes > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"The image exceeds the {settings.MAX_IMAGE_UPLOAD_BYTES // 1024 // 1024} MB limit.",
        )

    count = (
        await session.execute(
            select(func.count(MachineImage.id)).where(MachineImage.machine_model_id == machine.id)
        )
    ).scalar_one()
    if count >= settings.MAX_IMAGES_PER_MACHINE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This machine already has {count} images "
            f"(limit {settings.MAX_IMAGES_PER_MACHINE}). Delete one first.",
        )

    # El `order_index` lo asigna el servidor: el panel no debería tener que adivinar una
    # posición libre, y así el alta nunca puede chocar con `uq_machine_image_order`.
    highest = (
        await session.execute(
            select(func.max(MachineImage.order_index)).where(
                MachineImage.machine_model_id == machine.id
            )
        )
    ).scalar()

    # Dos commits, igual que el video: la clave del objeto lleva el id de la fila, así que la
    # fila tiene que existir antes de poder derivarla.
    image = MachineImage(
        machine_model_id=machine.id,
        original_filename=payload.filename,
        content_type=content_type,
        size_bytes=payload.size_bytes,
        alt_text=payload.alt_text,
        role=payload.role,
        order_index=0 if highest is None else highest + 1,
        is_ready=False,
    )
    session.add(image)
    await session.commit()
    await session.refresh(image)

    image.object_key = image_service.object_key_for(machine.id, image.id, content_type)
    session.add(image)
    await session.commit()
    await session.refresh(image)

    return schemas.MachineImageUploadTicket(
        image_id=image.id,
        upload_url=storage.presign_put(settings.MINIO_BUCKET_PUBLIC, image.object_key),
        object_key=image.object_key,
        public_url=image_service.public_url_for(image),
        expires_in_seconds=settings.MINIO_PRESIGN_TTL_SECONDS,
        required_content_type=content_type,
    )


@router.post(
    "/{machine_id}/images/{image_id}/confirm",
    response_model=schemas.MachineImageRead,
    dependencies=[Depends(require_backoffice)],
    summary="Confirm the upload finished and publish the image",
)
async def confirm_image(
    machine_id: uuid.UUID, image_id: uuid.UUID, session: SessionDep
) -> schemas.MachineImageRead:
    """Segunda fase, y **el único punto donde la validación es fiable**.

    `stat_object` devuelve el tamaño y el `Content-Type` que MinIO almacenó de verdad. Todo lo
    comprobado al pedir la URL era una declaración del cliente: una URL prefirmada no impone
    límite de tamaño, así que sin este paso alguien podría dejar un objeto enorme en un bucket
    público. Si no cuadra, se borra el objeto y la fila.
    """
    await _get_machine(session, machine_id)
    image = await _get_image(session, machine_id, image_id)

    try:
        stat = storage.get_client().stat_object(settings.MINIO_BUCKET_PUBLIC, image.object_key)
    except S3Error as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The file is not in storage. Did the upload finish?"
        ) from exc

    async def _discard() -> None:
        # `suppress`: si el objeto ya no está, el resultado que buscamos (que no quede) ya se
        # cumple. Lo que no puede fallar es el borrado de la fila.
        with contextlib.suppress(S3Error):
            storage.get_client().remove_object(settings.MINIO_BUCKET_PUBLIC, image.object_key)
        await session.delete(image)
        await session.commit()

    stored_type = image_service.normalise_content_type(stat.content_type or "")
    if not image_service.is_allowed_content_type(stored_type):
        await _discard()
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"The stored file is '{stored_type}', which is not an allowed image type.",
        )

    if stat.size and stat.size > settings.MAX_IMAGE_UPLOAD_BYTES:
        await _discard()
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"The uploaded image is {stat.size} bytes, over the "
            f"{settings.MAX_IMAGE_UPLOAD_BYTES} byte limit.",
        )

    image.size_bytes = stat.size
    image.content_type = stored_type
    image.is_ready = True
    if image.role is MachineImageRole.cover:
        await _demote_other_covers(session, machine_id, image.id)
    session.add(image)
    await session.commit()
    await session.refresh(image)

    return image_service.to_read(image)


@router.get(
    "/{machine_id}/images",
    response_model=list[schemas.MachineImageRead],
    summary="Images of a machine, ordered",
)
async def list_machine_images(
    machine_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[schemas.MachineImageRead]:
    """El trainee ve solo las confirmadas; el backoffice ve también las que se quedaron a medias,
    porque si no no tendría forma de encontrarlas para borrarlas."""
    await _get_machine(session, machine_id)
    gallery = (await image_service.load_for_machines(session, [machine_id])).get(machine_id, [])

    if user.role.is_backoffice:
        return [image_service.to_read(image) for image in gallery]
    return image_service.to_reads(gallery)


@router.patch(
    "/{machine_id}/images/{image_id}",
    response_model=schemas.MachineImageRead,
    dependencies=[Depends(require_backoffice)],
    summary="Reorder an image, edit its alt text or make it the cover",
)
async def update_machine_image(
    machine_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: schemas.MachineImageUpdate,
    session: SessionDep,
) -> schemas.MachineImageRead:
    await _get_machine(session, machine_id)
    image = await _get_image(session, machine_id, image_id)
    changes = payload.model_dump(exclude_unset=True)

    new_index = changes.get("order_index")
    if new_index is not None and new_index != image.order_index:
        # Pre-check para devolver un 409 legible en lugar de dejar que estalle la restricción
        # única como un 500. Mismo criterio que los módulos y lecciones del LMS.
        clash = (
            (
                await session.execute(
                    select(MachineImage).where(
                        MachineImage.machine_model_id == machine_id,
                        MachineImage.order_index == new_index,
                        MachineImage.id != image.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"An image already exists at position {new_index} for this machine.",
            )

    for key, value in changes.items():
        setattr(image, key, value)

    if changes.get("role") == MachineImageRole.cover:
        await _demote_other_covers(session, machine_id, image.id)

    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image_service.to_read(image)


@router.delete(
    "/{machine_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_backoffice)],
    summary="Delete an image",
)
async def delete_machine_image(
    machine_id: uuid.UUID, image_id: uuid.UUID, session: SessionDep
) -> Response:
    await _get_machine(session, machine_id)
    image = await _get_image(session, machine_id, image_id)

    # Primero el objeto y luego la fila, tolerando que el objeto ya no esté: si se borra la fila
    # primero y falla el objeto, queda basura en MinIO que nadie sabe ya a qué correspondía.
    if image.object_key:
        with contextlib.suppress(S3Error):
            storage.get_client().remove_object(settings.MINIO_BUCKET_PUBLIC, image.object_key)

    await session.delete(image)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{machine_id}/qr.png",
    dependencies=[Depends(require_backoffice)],
    summary="QR code as PNG for printing",
    response_class=Response,
)
async def machine_qr_png(machine_id: uuid.UUID, session: SessionDep) -> Response:
    machine = await _get_machine(session, machine_id)
    return Response(
        content=qr_service.png_bytes(machine.qr_token),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="qr-{machine.code}.png"'},
    )


@router.get(
    "/{machine_id}/qr.svg",
    dependencies=[Depends(require_backoffice)],
    summary="QR code as vector SVG for print",
    response_class=Response,
)
async def machine_qr_svg(machine_id: uuid.UUID, session: SessionDep) -> Response:
    machine = await _get_machine(session, machine_id)
    return Response(
        content=qr_service.svg_bytes(machine.qr_token),
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="qr-{machine.code}.svg"'},
    )


@router.get(
    "/{machine_id}/qr-data",
    dependencies=[Depends(require_backoffice)],
    summary="QR data as plain text for export to other systems",
)
async def machine_qr_data(machine_id: uuid.UUID, session: SessionDep) -> dict:
    machine = await _get_machine(session, machine_id)
    return qr_service.export_payload(machine)
