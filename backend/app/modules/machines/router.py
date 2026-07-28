"""Endpoints de máquinas: catálogo, QR y resolución del deep link."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, SessionDep, require_backoffice
from app.modules.machines import qr_service
from app.modules.machines.models import MachineModel, PublishStatus, Specialty

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

    El progreso viene aquí, agregado en **dos consultas fijas**, y no en una llamada por máquina:
    la app pinta el porcentaje en cada tarjeta del catálogo, así que resolverlo con
    `/lms/machines/{id}/path` sería un N+1 que crece con el catálogo.
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

    return MachineResolved(
        machine_model_id=machine.id,
        code=machine.code,
        name=machine.name,
        specialty=machine.specialty,
        description=machine.description,
        modules_count=len(list(modules.scalars())),
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
    return MachineRead(**machine.model_dump())


async def _get_machine(session: AsyncSession, machine_id: uuid.UUID) -> MachineModel:
    machine = await session.get(MachineModel, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.")
    return machine


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
