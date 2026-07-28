"""Lógica del LMS: ruta de aprendizaje con progreso y bloqueo por prerrequisito."""

from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import utcnow
from app.core.config import settings
from app.modules.lms import schemas
from app.modules.lms.models import (
    Lesson,
    ProgressStatus,
    TrainingModule,
    UserLessonProgress,
    VideoAsset,
    VideoStatus,
)
from app.modules.machines.models import MachineModel, PublishStatus


async def record_progress(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson: Lesson,
    position_seconds: float,
    duration_seconds: float | None,
) -> UserLessonProgress:
    """Registra el avance del reproductor de forma idempotente.

    Tres reglas que importan:

    1. **UPSERT sobre (user_id, lesson_id).** El reproductor manda un heartbeat cada pocos
       segundos; sin la restricción única y el `ON CONFLICT` esto acumularía miles de filas
       por usuario y lección.
    2. **`watched_percent` nunca baja.** Se guarda el máximo histórico. Rebobinar para repasar
       algo no debe reducir el progreso ya conseguido.
    3. **El porcentaje lo calcula el servidor** a partir de la duración real del video. Si lo
       enviara el cliente, completar una lección sin verla sería un `PUT` con `100`.
    """
    position = max(0.0, position_seconds)
    if duration_seconds and duration_seconds > 0:
        # Se acota a 100: la última posición reportada puede exceder ligeramente la duración.
        percent = min(100.0, position / duration_seconds * 100.0)
    else:
        # Sin duración conocida (lección de texto o PDF) abrirla ya cuenta como completada:
        # no hay forma de medir "cuánto" se leyó, y un progreso que nunca avanza es peor.
        percent = 100.0

    now = utcnow()
    threshold = settings.LESSON_COMPLETION_PERCENT
    table = UserLessonProgress.__table__

    # El porcentaje efectivo es el máximo entre el guardado y el nuevo. Se calcula en SQL con
    # GREATEST en lugar de leer-modificar-escribir: una sola ida a la base de datos y sin
    # condición de carrera entre dos heartbeats concurrentes del mismo reproductor.
    best_percent = func.greatest(table.c.watched_percent, percent)
    is_complete = best_percent >= threshold

    statement = (
        pg_insert(UserLessonProgress)
        .values(
            user_id=user_id,
            lesson_id=lesson.id,
            status=(
                ProgressStatus.completed if percent >= threshold else ProgressStatus.in_progress
            ).value,
            last_position_seconds=position,
            watched_percent=percent,
            completed_at=now if percent >= threshold else None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "lesson_id"],
            set_={
                "last_position_seconds": position,
                "watched_percent": best_percent,
                # El estado se deriva del máximo histórico, no del último heartbeat: rebobinar
                # una lección ya completada no la devuelve a "en curso".
                "status": case(
                    (is_complete, ProgressStatus.completed.value),
                    else_=ProgressStatus.in_progress.value,
                ),
                # `completed_at` se sella una sola vez. La fecha de finalización es lo que
                # acabará en el certificado; no puede moverse cada vez que se reabre la lección.
                "completed_at": case(
                    (table.c.completed_at.isnot(None), table.c.completed_at),
                    (is_complete, now),
                    else_=None,
                ),
                "updated_at": now,
            },
        )
    )

    await session.execute(statement)
    await session.commit()

    result = await session.execute(
        select(UserLessonProgress).where(
            UserLessonProgress.user_id == user_id,
            UserLessonProgress.lesson_id == lesson.id,
        )
    )
    return result.scalars().one()


def _empty_progress() -> schemas.LessonProgressRead:
    return schemas.LessonProgressRead(
        status=ProgressStatus.not_started,
        last_position_seconds=0.0,
        watched_percent=0.0,
        completed_at=None,
    )


async def build_learning_path(
    session: AsyncSession,
    *,
    machine: MachineModel,
    user_id: uuid.UUID,
    include_drafts: bool,
) -> schemas.LearningPath:
    """Ensambla la ruta completa con el progreso del usuario.

    Se hacen 4 consultas fijas (módulos, lecciones, assets de video, progreso) y el ensamblado
    ocurre en memoria. La alternativa —consultar el progreso por lección— es N+1: con 8
    módulos de 5 lecciones serían 41 consultas por cada apertura de la pantalla principal de
    la app.
    """
    module_stmt = (
        select(TrainingModule)
        .where(TrainingModule.machine_model_id == machine.id)
        .order_by(TrainingModule.order_index)
    )
    if not include_drafts:
        module_stmt = module_stmt.where(TrainingModule.status == PublishStatus.published)
    modules = list((await session.execute(module_stmt)).scalars())

    if not modules:
        return schemas.LearningPath(
            machine_model_id=machine.id,
            machine_name=machine.name,
            machine_code=machine.code,
            total_lessons=0,
            completed_lessons=0,
            progress_percent=0.0,
            modules=[],
        )

    module_ids = [module.id for module in modules]
    lesson_stmt = (
        select(Lesson).where(Lesson.training_module_id.in_(module_ids)).order_by(Lesson.order_index)
    )
    if not include_drafts:
        lesson_stmt = lesson_stmt.where(Lesson.status == PublishStatus.published)
    lessons = list((await session.execute(lesson_stmt)).scalars())

    asset_ids = [lesson.video_asset_id for lesson in lessons if lesson.video_asset_id]
    ready_assets: dict[uuid.UUID, VideoAsset] = {}
    if asset_ids:
        assets = await session.execute(select(VideoAsset).where(VideoAsset.id.in_(asset_ids)))
        ready_assets = {asset.id: asset for asset in assets.scalars()}

    lesson_ids = [lesson.id for lesson in lessons]
    progress_map: dict[uuid.UUID, UserLessonProgress] = {}
    if lesson_ids:
        rows = await session.execute(
            select(UserLessonProgress).where(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.lesson_id.in_(lesson_ids),
            )
        )
        progress_map = {row.lesson_id: row for row in rows.scalars()}

    lessons_by_module: dict[uuid.UUID, list[Lesson]] = {module_id: [] for module_id in module_ids}
    for lesson in lessons:
        lessons_by_module[lesson.training_module_id].append(lesson)

    modules_out: list[schemas.ModuleInPath] = []
    total_lessons = 0
    total_completed = 0
    # El bloqueo es secuencial: un módulo con `requires_previous` se abre solo si el anterior
    # está completo al 100%.
    previous_complete = True

    for module in modules:
        module_lessons = lessons_by_module[module.id]
        completed_here = 0
        lessons_out: list[schemas.LessonInPath] = []

        for lesson in module_lessons:
            row = progress_map.get(lesson.id)
            progress = (
                schemas.LessonProgressRead(
                    status=row.status,
                    last_position_seconds=row.last_position_seconds,
                    watched_percent=row.watched_percent,
                    completed_at=row.completed_at,
                )
                if row
                else _empty_progress()
            )
            if progress.status is ProgressStatus.completed:
                completed_here += 1

            asset = ready_assets.get(lesson.video_asset_id) if lesson.video_asset_id else None
            lessons_out.append(
                schemas.LessonInPath(
                    id=lesson.id,
                    title=lesson.title,
                    content_type=lesson.content_type,
                    order_index=lesson.order_index,
                    estimated_minutes=lesson.estimated_minutes,
                    has_video=lesson.video_asset_id is not None,
                    video_ready=asset is not None and asset.status is VideoStatus.ready,
                    progress=progress,
                )
            )

        locked = module.requires_previous and not previous_complete
        modules_out.append(
            schemas.ModuleInPath(
                id=module.id,
                title=module.title,
                description=module.description,
                order_index=module.order_index,
                locked=locked,
                completed_lessons=completed_here,
                total_lessons=len(module_lessons),
                lessons=lessons_out,
            )
        )

        total_lessons += len(module_lessons)
        total_completed += completed_here
        # Un módulo sin lecciones no debe bloquear el siguiente para siempre.
        previous_complete = len(module_lessons) == 0 or completed_here == len(module_lessons)

    return schemas.LearningPath(
        machine_model_id=machine.id,
        machine_name=machine.name,
        machine_code=machine.code,
        total_lessons=total_lessons,
        completed_lessons=total_completed,
        progress_percent=round(total_completed / total_lessons * 100, 1) if total_lessons else 0.0,
        modules=modules_out,
    )


async def is_lesson_accessible(
    session: AsyncSession, *, lesson: Lesson, user_id: uuid.UUID
) -> bool:
    """Comprueba el prerrequisito en el servidor.

    La app ya pinta el candado, pero eso es presentación: sin esta comprobación, saltarse el
    orden de la capacitación es un `GET` con el id de la lección. En una plataforma que emite
    certificados, el orden es parte de lo que se certifica.
    """
    module = await session.get(TrainingModule, lesson.training_module_id)
    if module is None:
        return False
    if not module.requires_previous or module.order_index == 0:
        return True

    previous = await session.execute(
        select(TrainingModule)
        .where(
            TrainingModule.machine_model_id == module.machine_model_id,
            TrainingModule.order_index < module.order_index,
            TrainingModule.status == PublishStatus.published,
        )
        .order_by(TrainingModule.order_index.desc())
        .limit(1)
    )
    previous_module = previous.scalars().first()
    if previous_module is None:
        return True

    previous_lessons = list(
        (
            await session.execute(
                select(Lesson.id).where(
                    Lesson.training_module_id == previous_module.id,
                    Lesson.status == PublishStatus.published,
                )
            )
        ).scalars()
    )
    if not previous_lessons:
        return True

    completed = list(
        (
            await session.execute(
                select(UserLessonProgress.lesson_id).where(
                    UserLessonProgress.user_id == user_id,
                    UserLessonProgress.lesson_id.in_(previous_lessons),
                    UserLessonProgress.status == ProgressStatus.completed,
                )
            )
        ).scalars()
    )
    return len(completed) == len(previous_lessons)
