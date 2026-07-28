"""Consultas agregadas del dashboard.

Un builder por sección, cada uno devolviendo su sub-modelo. Así partir el endpoint en varios
más adelante es un cambio de `router.py`, no una reescritura.

Todo el cálculo derivado (ratios, relleno de series, avisos) está en `derive.py`. Aquí solo hay
I/O y ensamblado.

**Los builders se ejecutan en serie, nunca con `asyncio.gather`.** No es un descuido de
rendimiento: asyncpg no multiplexa una conexión, así que dos consultas concurrentes sobre la
misma `AsyncSession` fallan con `InterfaceError: another operation is in progress`. Paralelizar
exigiría abrir sesiones independientes desde `AsyncSessionFactory`, consumiendo `DB_POOL_SIZE`
por builder. No vale la pena para agregados sobre decenas de filas.

Assessments (`QuizAttempt`, `Certificate`) se quedan fuera a propósito: no tienen router, así
que sus tablas están vacías **por construcción**, no por falta de uso. Un tile permanente de
"0 intentos" no comunica "función pendiente", comunica "función rota". Cuando aterrice el router
de assessments, entra aquí con un `GROUP BY passed` y un sub-modelo.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import Date, Select, case, cast, exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import (
    AgentConfig,
    Conversation,
    DocumentSourceType,
    IngestStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    Message,
    MessageRole,
    ProviderCredential,
    ToolDefinition,
    ToolInvocation,
)
from app.modules.auth.models import User, UserRole
from app.modules.lms.models import (
    Lesson,
    LessonContentType,
    ProgressStatus,
    TrainingModule,
    UserLessonProgress,
    VideoAsset,
    VideoStatus,
)
from app.modules.machines.models import MachineModel, PublishStatus, Specialty
from app.modules.stats.derive import (
    build_pending_actions,
    fill_daily_series,
    ratio_percent,
    to_opt_float,
    to_opt_int,
)
from app.modules.stats.schemas import (
    AgentActivityStats,
    ContentStats,
    DailyActivity,
    KnowledgeStats,
    LatencyStats,
    LessonCounters,
    MachineCounters,
    ModuleCounters,
    ProviderUsage,
    RecentConversation,
    SourceTypeCount,
    SpecialtyCount,
    StatsOverview,
    SystemHealthStats,
    TrainingStats,
    VideoCounters,
)

# Umbral para considerar que un trabajo asíncrono se quedó colgado. Generoso a propósito: un
# video largo tarda minutos, y un falso positivo en el dashboard enseña a ignorar los avisos.
STUCK_AFTER = timedelta(minutes=30)


def _bucket(enum_cls: type) -> dict[str, int]:
    """Diccionario con TODOS los miembros del enum a cero.

    Imprescindible, y es el fallo más probable del módulo si se omite: un `GROUP BY` no
    devuelve fila para los estados sin registros, así que indexar directamente el resultado
    lanza `KeyError` justo con los datos escasos de la demo.
    """
    return {member.value: 0 for member in enum_cls}


def _key(value: object) -> str:
    """Normaliza la clave de un `GROUP BY` sobre una columna de enum.

    `enum_type()` declara un `Enum` de SQLAlchemy (no un `String`), así que la fila devuelve el
    **miembro del enum**, no su `str`. Sin este `.value` la indexación falla.
    """
    return value.value if hasattr(value, "value") else str(value)


def window_bounds(days: int) -> tuple[datetime, datetime.date, datetime.date]:
    """Calcula la ventana temporal una sola vez, anclada a medianoche UTC.

    El borde inferior tiene que caer en medianoche y no en "hace N días": si se filtrase por
    `utcnow() - timedelta(days=N)`, la primera barra del gráfico sería un día parcial y saldría
    artificialmente baja, que parece un bajón de uso y no lo es.
    """
    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=days - 1)
    return datetime.combine(start_day, time.min, tzinfo=UTC), start_day, today


def _safe_sources_length():
    """Longitud del array `sources` de un mensaje, a prueba de valores no-array.

    Tres hechos que obligan a esto:

    1. La columna se declaró `JSON`, no `JSONB` (ver la migración inicial), así que
       `jsonb_array_length` **no compila**: no existe para el tipo `json`.
    2. `sa.JSON` persiste un `None` de Python como el literal JSON `null`, y
       `json_array_length('null'::json)` aborta con "cannot get array length of a scalar".
    3. La guarda tiene que ir **dentro** del argumento, no como condición hermana en un `AND`:
       Postgres no garantiza cortocircuito, así que `typeof = 'array' AND length > 0` puede
       evaluar la longitud sobre un escalar y tumbar la consulta entera.
    """
    safe = case(
        (func.json_typeof(Message.sources) == "array", Message.sources),
        else_=text("'[]'::json"),
    )
    return func.json_array_length(safe)


def _status_counts(status_column) -> Select:
    return select(status_column, func.count().label("total")).group_by(status_column)


# =============================================================================
#  Contenido
# =============================================================================
async def build_content_stats(session: AsyncSession) -> ContentStats:
    machine_buckets = _bucket(PublishStatus)
    for row in await session.execute(_status_counts(MachineModel.status)):
        machine_buckets[_key(row.status)] = row.total

    # Máquinas publicadas sin módulos publicados: el dato más accionable para un editor de
    # contenido, porque significa un QR pegado a un equipo que no lleva a ninguna parte.
    orphan_machines = await session.scalar(
        select(func.count())
        .select_from(MachineModel)
        .where(
            MachineModel.status == PublishStatus.published,
            ~exists(
                select(1)
                .select_from(TrainingModule)
                .where(
                    TrainingModule.machine_model_id == MachineModel.id,
                    TrainingModule.status == PublishStatus.published,
                )
                .correlate(MachineModel)
            ),
        )
    )

    by_specialty_rows = await session.execute(
        select(
            MachineModel.specialty,
            func.count().label("total"),
            func.count().filter(MachineModel.status == PublishStatus.published).label("published"),
        ).group_by(MachineModel.specialty)
    )
    by_specialty = [
        SpecialtyCount(
            specialty=Specialty(_key(row.specialty)), total=row.total, published=row.published
        )
        for row in by_specialty_rows
    ]

    module_buckets = _bucket(PublishStatus)
    for row in await session.execute(_status_counts(TrainingModule.status)):
        module_buckets[_key(row.status)] = row.total

    lesson_buckets = _bucket(PublishStatus)
    for row in await session.execute(_status_counts(Lesson.status)):
        lesson_buckets[_key(row.status)] = row.total

    type_buckets = _bucket(LessonContentType)
    for row in await session.execute(_status_counts(Lesson.content_type)):
        type_buckets[_key(row.content_type)] = row.total

    lesson_extra = (
        await session.execute(
            select(
                # SUM sí se colapsa a 0: sumar cero lecciones son cero minutos, y eso es verdad.
                func.coalesce(func.sum(Lesson.estimated_minutes), 0).label("minutes"),
                func.count()
                .filter(
                    Lesson.content_type == LessonContentType.video,
                    Lesson.video_asset_id.is_(None),
                )
                .label("video_without_asset"),
            )
        )
    ).one()

    video_rows = await session.execute(
        select(
            VideoAsset.status,
            func.count().label("total"),
            func.sum(VideoAsset.duration_seconds).label("duration_seconds"),
            func.sum(VideoAsset.size_bytes).label("size_bytes"),
        ).group_by(VideoAsset.status)
    )
    video_buckets = _bucket(VideoStatus)
    ready_seconds: float | None = None
    total_bytes: float | None = None
    for row in video_rows:
        video_buckets[_key(row.status)] = row.total
        # Ambas columnas son nullable, así que el SUM del grupo puede salir NULL. Solo se
        # acumula cuando hay valor: "no lo sé" y "cero" no son lo mismo.
        if row.size_bytes is not None:
            total_bytes = (total_bytes or 0.0) + float(row.size_bytes)
        if _key(row.status) == VideoStatus.ready.value and row.duration_seconds is not None:
            ready_seconds = float(row.duration_seconds)

    return ContentStats(
        machines=MachineCounters(
            total=sum(machine_buckets.values()),
            draft=machine_buckets[PublishStatus.draft.value],
            published=machine_buckets[PublishStatus.published.value],
            archived=machine_buckets[PublishStatus.archived.value],
            published_without_content=orphan_machines or 0,
            by_specialty=by_specialty,
        ),
        modules=ModuleCounters(
            total=sum(module_buckets.values()),
            draft=module_buckets[PublishStatus.draft.value],
            published=module_buckets[PublishStatus.published.value],
            archived=module_buckets[PublishStatus.archived.value],
        ),
        lessons=LessonCounters(
            total=sum(lesson_buckets.values()),
            draft=lesson_buckets[PublishStatus.draft.value],
            published=lesson_buckets[PublishStatus.published.value],
            archived=lesson_buckets[PublishStatus.archived.value],
            video=type_buckets[LessonContentType.video.value],
            pdf=type_buckets[LessonContentType.pdf.value],
            text=type_buckets[LessonContentType.text.value],
            video_without_asset=lesson_extra.video_without_asset,
            estimated_minutes_total=int(lesson_extra.minutes or 0),
        ),
        videos=VideoCounters(
            total=sum(video_buckets.values()),
            uploaded=video_buckets[VideoStatus.uploaded.value],
            queued=video_buckets[VideoStatus.queued.value],
            processing=video_buckets[VideoStatus.processing.value],
            ready=video_buckets[VideoStatus.ready.value],
            failed=video_buckets[VideoStatus.failed.value],
            ready_minutes=round(ready_seconds / 60, 1) if ready_seconds is not None else None,
            total_size_mb=round(total_bytes / 1_048_576, 1) if total_bytes is not None else None,
        ),
    )


# =============================================================================
#  RAG
# =============================================================================
async def build_knowledge_stats(session: AsyncSession) -> KnowledgeStats:
    doc_buckets = _bucket(IngestStatus)
    for row in await session.execute(_status_counts(KnowledgeDocument.status)):
        doc_buckets[_key(row.status)] = row.total

    doc_extra = (
        await session.execute(
            select(
                func.count().filter(KnowledgeDocument.machine_model_id.is_(None)).label("global_"),
                func.coalesce(func.sum(KnowledgeDocument.chunk_count), 0).label("declared_chunks"),
                func.max(KnowledgeDocument.indexed_at).label("last_indexed_at"),
            )
        )
    ).one()

    by_source_rows = await session.execute(_status_counts(KnowledgeDocument.source_type))
    by_source = [
        SourceTypeCount(source_type=DocumentSourceType(_key(row.source_type)), total=row.total)
        for row in by_source_rows
    ]

    chunk_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(KnowledgeChunk.is_global.is_(True)).label("global_"),
            )
        )
    ).one()

    embedding_models = list(
        (await session.execute(select(KnowledgeChunk.embedding_model).distinct())).scalars()
    )

    indexed = doc_buckets[IngestStatus.indexed.value]
    return KnowledgeStats(
        documents_total=sum(doc_buckets.values()),
        documents_pending=doc_buckets[IngestStatus.pending.value],
        documents_processing=doc_buckets[IngestStatus.processing.value],
        documents_indexed=indexed,
        documents_failed=doc_buckets[IngestStatus.failed.value],
        documents_global=doc_extra.global_,
        documents_by_source_type=by_source,
        chunks_total=chunk_row.total,
        chunks_global=chunk_row.global_,
        declared_chunk_count_total=int(doc_extra.declared_chunks or 0),
        embedding_models=sorted(embedding_models),
        # Media, así que nunca se colapsa: sin documentos indexados no hay media que dar.
        average_chunks_per_indexed_document=(
            round(chunk_row.total / indexed, 1) if indexed > 0 else None
        ),
        last_indexed_at=doc_extra.last_indexed_at,
    )


# =============================================================================
#  Actividad del agente
# =============================================================================
async def build_agent_activity(
    session: AsyncSession,
    *,
    days: int,
    window_start: datetime,
    start_day: datetime.date,
    today: datetime.date,
) -> AgentActivityStats:
    conversation_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(Conversation.created_at >= window_start).label("in_window"),
                func.count().filter(Conversation.is_archived.is_(True)).label("archived"),
                func.count()
                .filter(Conversation.machine_model_id.is_not(None))
                .label("with_machine"),
                func.count(func.distinct(Conversation.user_id))
                .filter(Conversation.created_at >= window_start)
                .label("distinct_users"),
            )
        )
    ).one()

    message_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(Message.created_at >= window_start).label("in_window"),
                func.count()
                .filter(
                    Message.created_at >= window_start,
                    Message.role == MessageRole.assistant,
                )
                .label("assistant"),
                func.coalesce(
                    func.sum(
                        case((Message.created_at >= window_start, Message.prompt_tokens), else_=0)
                    ),
                    0,
                ).label("prompt_tokens"),
                func.coalesce(
                    func.sum(
                        case(
                            (Message.created_at >= window_start, Message.completion_tokens), else_=0
                        )
                    ),
                    0,
                ).label("completion_tokens"),
                func.count()
                .filter(
                    Message.created_at >= window_start,
                    Message.role == MessageRole.assistant,
                    _safe_sources_length() > 0,
                )
                .label("grounded"),
            )
        )
    ).one()

    # Percentiles en SQL y con `percentile_disc`, no `percentile_cont`: con 3 muestras, `cont`
    # interpola y devuelve un número de milisegundos que ninguna petición tardó nunca. En un
    # dashboard eso es un dato inventado. Sobre cero filas ambos devuelven NULL, que es
    # exactamente la semántica que queremos.
    latency_row = (
        await session.execute(
            select(
                func.count().label("sample_size"),
                func.percentile_disc(0.5).within_group(Message.latency_ms.asc()).label("p50"),
                func.percentile_disc(0.95).within_group(Message.latency_ms.asc()).label("p95"),
                func.avg(Message.latency_ms).label("avg"),
                func.max(Message.latency_ms).label("max"),
            ).where(
                Message.created_at >= window_start,
                Message.role == MessageRole.assistant,
                Message.latency_ms.is_not(None),
            )
        )
    ).one()

    # `provider` es nullable y los mensajes de rol `user` lo tienen a NULL, de ahí el filtro por
    # rol: sin él, el desglose por proveedor tendría una fila "unknown" con la mitad del tráfico.
    # Se agrupa por la columna cruda, con NULL como su propio grupo, y el "unknown" se pone en
    # Python. Agrupar por `coalesce(provider, 'unknown')` parece más limpio pero NO funciona:
    # SQLAlchemy emite un bind param distinto en el SELECT y en el GROUP BY, y Postgres no
    # reconoce dos placeholders como la misma expresión ("must appear in the GROUP BY clause").
    provider_rows = await session.execute(
        select(
            Message.provider,
            func.count().label("messages"),
            func.coalesce(func.sum(func.coalesce(Message.prompt_tokens, 0)), 0).label(
                "prompt_tokens"
            ),
            func.coalesce(func.sum(func.coalesce(Message.completion_tokens, 0)), 0).label(
                "completion_tokens"
            ),
            func.avg(Message.latency_ms).label("avg_latency"),
        )
        .where(Message.created_at >= window_start, Message.role == MessageRole.assistant)
        .group_by(Message.provider)
        .order_by(func.count().desc())
    )
    by_provider = [
        ProviderUsage(
            provider=row.provider or "unknown",
            assistant_messages=row.messages,
            total_tokens=int(row.prompt_tokens) + int(row.completion_tokens),
            avg_latency_ms=to_opt_float(row.avg_latency, digits=0),
        )
        for row in provider_rows
    ]

    # `date_trunc` usa el TimeZone de la sesión, así que un cambio de configuración de Postgres
    # movería los límites de los días sin que nadie toque código. Se ancla a UTC explícitamente.
    conv_day = cast(func.timezone("UTC", Conversation.created_at), Date)
    msg_day = cast(func.timezone("UTC", Message.created_at), Date)

    conv_series = {
        row.day: row.total
        for row in await session.execute(
            select(conv_day.label("day"), func.count().label("total"))
            .where(Conversation.created_at >= window_start)
            .group_by(conv_day)
        )
    }
    msg_series = {
        row.day: row.total
        for row in await session.execute(
            select(msg_day.label("day"), func.count().label("total"))
            .where(Message.created_at >= window_start)
            .group_by(msg_day)
        )
    }

    tool_calls = await session.scalar(
        select(func.count())
        .select_from(ToolInvocation)
        .where(ToolInvocation.created_at >= window_start)
    )

    return AgentActivityStats(
        window_days=days,
        window_start=start_day,
        window_end=today,
        conversations_total=conversation_row.total,
        conversations_in_window=conversation_row.in_window,
        conversations_archived=conversation_row.archived,
        conversations_with_machine_context=conversation_row.with_machine,
        distinct_users_in_window=conversation_row.distinct_users,
        messages_total=message_row.total,
        messages_in_window=message_row.in_window,
        assistant_messages_in_window=message_row.assistant,
        prompt_tokens_total=int(message_row.prompt_tokens),
        completion_tokens_total=int(message_row.completion_tokens),
        tokens_total=int(message_row.prompt_tokens) + int(message_row.completion_tokens),
        grounded_assistant_messages=message_row.grounded,
        grounded_answer_percent=ratio_percent(message_row.grounded, message_row.assistant),
        tool_invocations_in_window=tool_calls or 0,
        latency=LatencyStats(
            sample_size=latency_row.sample_size,
            p50_ms=to_opt_int(latency_row.p50),
            p95_ms=to_opt_int(latency_row.p95),
            avg_ms=to_opt_float(latency_row.avg, digits=0),
            max_ms=to_opt_int(latency_row.max),
        ),
        by_provider=by_provider,
        daily=fill_daily_series(
            anchor=today, days=days, conversations=conv_series, messages=msg_series
        ),
    )


# =============================================================================
#  Salud del sistema
# =============================================================================
async def build_system_health(
    session: AsyncSession,
    *,
    window_start: datetime,
    content: ContentStats,
    knowledge: KnowledgeStats,
) -> SystemHealthStats:
    stuck_before = datetime.now(UTC) - STUCK_AFTER

    credential_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(ProviderCredential.is_active.is_(True)).label("active"),
                func.count()
                .filter(
                    ProviderCredential.is_active.is_(True),
                    ProviderCredential.last_check_ok.is_(False),
                )
                .label("failing"),
                func.count()
                .filter(
                    ProviderCredential.is_active.is_(True),
                    ProviderCredential.last_check_ok.is_(None),
                )
                .label("never_checked"),
            )
        )
    ).one()

    config_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(AgentConfig.is_active.is_(True)).label("active"),
                func.count()
                .filter(AgentConfig.is_active.is_(True), AgentConfig.is_default.is_(True))
                .label("default_"),
            )
        )
    ).one()

    tool_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(ToolDefinition.is_active.is_(True)).label("active"),
            )
        )
    ).one()

    invocation_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count()
                .filter(
                    (ToolInvocation.status_code >= 400)
                    | (ToolInvocation.error_message.is_not(None))
                )
                .label("errors"),
            ).where(ToolInvocation.created_at >= window_start)
        )
    ).one()

    stuck_videos = await session.scalar(
        select(func.count())
        .select_from(VideoAsset)
        .where(
            VideoAsset.status == VideoStatus.processing,
            VideoAsset.processing_started_at < stuck_before,
        )
    )
    stuck_documents = await session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(
            KnowledgeDocument.status == IngestStatus.processing,
            KnowledgeDocument.updated_at < stuck_before,
        )
    )

    return SystemHealthStats(
        provider_credentials_total=credential_row.total,
        provider_credentials_active=credential_row.active,
        provider_credentials_failing_check=credential_row.failing,
        provider_credentials_never_checked=credential_row.never_checked,
        agent_configs_total=config_row.total,
        agent_configs_active=config_row.active,
        has_default_agent_config=config_row.default_ > 0,
        tools_total=tool_row.total,
        tools_active=tool_row.active,
        tool_invocations_in_window=invocation_row.total,
        tool_invocation_errors_in_window=invocation_row.errors,
        tool_error_percent=ratio_percent(invocation_row.errors, invocation_row.total),
        videos_failed=content.videos.failed,
        videos_stuck_processing=stuck_videos or 0,
        documents_failed=knowledge.documents_failed,
        documents_stuck_processing=stuck_documents or 0,
    )


# =============================================================================
#  Formación
# =============================================================================
async def build_training_stats(session: AsyncSession, *, window_start: datetime) -> TrainingStats:
    """Progreso de formación, **excluyendo cuentas demo**.

    La exclusión es asimétrica respecto a la sección del agente, que sí las cuenta, y está
    declarada en el payload (`excludes_demo_users`). El motivo: la cuenta demo es *compartida*,
    así que "12 lecciones completadas" por un único login no mide adopción, la falsea. En
    cambio los tokens y la latencia de esa misma cuenta son coste y salud reales.
    """
    user_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(User.is_active.is_(True)).label("active"),
                func.count().filter(User.role == UserRole.trainee).label("trainees"),
                func.count().filter(User.last_login_at >= window_start).label("logged_in"),
            ).where(User.is_demo.is_(False))
        )
    ).one()

    progress_rows = await session.execute(
        select(
            UserLessonProgress.status,
            func.count().label("total"),
            func.avg(UserLessonProgress.watched_percent).label("avg_watched"),
        )
        .join(User, User.id == UserLessonProgress.user_id)
        .where(User.is_demo.is_(False))
        .group_by(UserLessonProgress.status)
    )
    progress_buckets = _bucket(ProgressStatus)
    weighted_sum = 0.0
    for row in progress_rows:
        progress_buckets[_key(row.status)] = row.total
        average = to_opt_float(row.avg_watched)
        if average is not None:
            weighted_sum += average * row.total

    progress_total = sum(progress_buckets.values())
    completed_in_window = await session.scalar(
        select(func.count())
        .select_from(UserLessonProgress)
        .join(User, User.id == UserLessonProgress.user_id)
        .where(User.is_demo.is_(False), UserLessonProgress.completed_at >= window_start)
    )

    active_progress = await session.scalar(
        select(func.count(func.distinct(UserLessonProgress.user_id)))
        .join(User, User.id == UserLessonProgress.user_id)
        .where(User.is_demo.is_(False), UserLessonProgress.updated_at >= window_start)
    )

    completed = progress_buckets[ProgressStatus.completed.value]
    return TrainingStats(
        users_total=user_row.total,
        users_active=user_row.active,
        trainees_total=user_row.trainees,
        users_logged_in_in_window=user_row.logged_in,
        progress_rows_total=progress_total,
        lessons_in_progress=progress_buckets[ProgressStatus.in_progress.value],
        lessons_completed=completed,
        lessons_completed_in_window=completed_in_window or 0,
        average_watched_percent=(
            round(weighted_sum / progress_total, 1) if progress_total > 0 else None
        ),
        completion_percent=ratio_percent(completed, progress_total),
        active_users_in_window=active_progress or 0,
    )


# =============================================================================
#  Orquestación
# =============================================================================
async def build_overview(session: AsyncSession, *, days: int) -> StatsOverview:
    window_start, start_day, today = window_bounds(days)

    content = await build_content_stats(session)
    knowledge = await build_knowledge_stats(session)
    agent = await build_agent_activity(
        session, days=days, window_start=window_start, start_day=start_day, today=today
    )
    health = await build_system_health(
        session, window_start=window_start, content=content, knowledge=knowledge
    )
    training = await build_training_stats(session, window_start=window_start)

    return StatsOverview(
        generated_at=datetime.now(UTC),
        window_days=days,
        content=content,
        knowledge=knowledge,
        agent=agent,
        health=health,
        training=training,
        pending_actions=build_pending_actions(content=content, knowledge=knowledge, health=health),
        recent_conversations=await recent_conversations(session),
    )


def _truncate(text: str | None, limit: int = 90) -> str | None:
    """Recorta la pregunta para la tabla del dashboard, sin partir a mitad de palabra."""
    if not text:
        return None
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: clean.rfind(" ", 0, limit)] + "…"


async def recent_conversations(
    session: AsyncSession, *, limit: int = 10
) -> list[RecentConversation]:
    """Últimas conversaciones con su recuento de mensajes y latencia mediana.

    Es la tarjeta que mejor aparenta con datos mínimos: seis filas llenan una tabla de forma
    natural, mientras que seis puntos no llenan un gráfico.
    """
    message_stats = (
        select(
            Message.conversation_id.label("conversation_id"),
            func.count().label("message_count"),
            func.percentile_disc(0.5)
            .within_group(Message.latency_ms.asc())
            .filter(Message.latency_ms.is_not(None))
            .label("p50_ms"),
            func.max(Message.provider).label("provider"),
            # Primera pregunta del usuario, para cuando la conversación no tiene título. El chat
            # del WebSocket no lo pone, así que sin esto la columna sale vacía justo en las
            # conversaciones más recientes, que son las que el dashboard enseña.
            func.min(Message.content)
            .filter(Message.role == MessageRole.user)
            .label("first_question"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    rows = await session.execute(
        select(
            Conversation.id,
            Conversation.created_at,
            Conversation.title,
            User.full_name,
            MachineModel.code,
            MachineModel.name.label("machine_name"),
            func.coalesce(message_stats.c.message_count, 0).label("message_count"),
            message_stats.c.p50_ms,
            message_stats.c.provider,
            message_stats.c.first_question,
        )
        .join(User, User.id == Conversation.user_id)
        .outerjoin(MachineModel, MachineModel.id == Conversation.machine_model_id)
        .outerjoin(message_stats, message_stats.c.conversation_id == Conversation.id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )

    return [
        RecentConversation(
            id=str(row.id),
            created_at=row.created_at,
            title=row.title or _truncate(row.first_question),
            user_name=row.full_name,
            machine_code=row.code,
            machine_name=row.machine_name,
            message_count=row.message_count,
            p50_ms=to_opt_int(row.p50_ms),
            provider=row.provider,
        )
        for row in rows
    ]


__all__ = [
    "DailyActivity",
    "build_agent_activity",
    "build_content_stats",
    "build_knowledge_stats",
    "build_overview",
    "build_system_health",
    "build_training_stats",
    "recent_conversations",
    "window_bounds",
]
