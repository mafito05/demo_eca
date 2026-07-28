"""Siembra actividad histórica para que el dashboard tenga algo que graficar.

**No entra en `seed_demo.py` a propósito.** El seed base crea el contenido mínimo del producto y
tiene que seguir siendo la verdad; esto es material de escenografía para la reunión. Separarlo
mantiene esa frontera visible, y hace que ejecutarlo sea una decisión consciente.

Qué genera, repartido en las últimas tres semanas:

- Cuatro cuentas de formación (`trainee-*@demoeca.example.com`), **no demo**, para que las
  métricas de adopción tengan sujetos reales. La cuenta demo está excluida de esa sección
  precisamente porque es compartida.
- Conversaciones con sus mensajes de usuario y de asistente, con `provider`, tokens y
  `latency_ms` tomados del rango que el sistema produce de verdad (el smoke test mide p50 ~2,3 s
  y p95 ~4,5 s con OpenAI, y ~1000-1200 tokens por intercambio).
- Progreso de lecciones en los tres estados, con `watched_percent` coherente.

Todo con una semilla fija: dos ejecuciones producen los mismos números, así que una captura de
pantalla del dashboard sigue siendo válida mañana.

Las respuestas del asistente llevan `sources` reales del documento sembrado cuando existe, para
que el KPI de "respuestas con fuente citada" no salga inventado.

    docker compose exec backend python -m scripts.seed_demo_activity
    docker compose exec backend python -m scripts.seed_demo_activity --purge   # revertir
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionFactory, engine
from app.core.security import hash_password

# Importar el paquete completo registra todas las tablas: sin esto, las relaciones no resuelven
# y SQLAlchemy lanza NoReferencedTableError al primer JOIN.
from app.models import *  # noqa: F403
from app.modules.agent.models import (
    Conversation,
    KnowledgeDocument,
    Message,
    MessageRole,
)
from app.modules.auth.models import User, UserRole
from app.modules.lms.models import Lesson, ProgressStatus, TrainingModule, UserLessonProgress
from app.modules.machines.models import MachineModel, PublishStatus

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed-activity")

SEED = 20260727
WINDOW_DAYS = 21

TRAINEES = [
    ("trainee-nadia@demoeca.example.com", "Nadia Okonkwo", "Urology", "Demo Hospital"),
    ("trainee-marc@demoeca.example.com", "Marc Petit", "Biomedical Engineering", "Demo Hospital"),
    ("trainee-sofia@demoeca.example.com", "Sofia Duarte", "Urology", "Northside Clinic"),
    ("trainee-kenji@demoeca.example.com", "Kenji Watanabe", "Clinical Technology", "Demo Hospital"),
]

# Pares pregunta/respuesta plausibles contra el manual sembrado. La respuesta importa poco para
# los KPIs, pero un dashboard con lorem ipsum en la tabla de actividad reciente se nota.
EXCHANGES = [
    (
        "What should I do if the unit shows error E-204?",
        "E-204 is a transducer continuity failure. Check the rear connector and run routine "
        "CAL-01 again. If it fails a second time, the transducer needs replacing.",
        "4. COMMON FAULT RESOLUTION",
    ),
    (
        "How often does the coupling fluid need replacing?",
        "Every 300 shots or every 30 days, whichever comes first.",
        "5. PREVENTIVE MAINTENANCE",
    ),
    (
        "What is the valid transducer range after CAL-01?",
        "The reference value must fall between 0.95 and 1.05. Outside that range, repeat the "
        "routine.",
        "2. DAILY CALIBRATION",
    ),
    (
        "Can I fire the unit with the therapy head uncoupled?",
        "No. Firing without coupling medium causes irreversible damage to the membrane. The "
        "manual flags this as a warning.",
        "3. OPERATOR SAFETY",
    ),
    (
        "The unit is overheating, what do I do?",
        "That is E-330. Allow 15 minutes of cooling with the unit powered on so the fan keeps "
        "running — do not power it off.",
        "4. COMMON FAULT RESOLUTION",
    ),
    (
        "What is the minimum coupling fluid level?",
        "The operating range is 1.8 to 2.2 litres. Below 1.8 L the unit blocks firing.",
        "1. EQUIPMENT PREPARATION",
    ),
    (
        "How long does the self-test take?",
        "Approximately 90 seconds after powering on.",
        "2. DAILY CALIBRATION",
    ),
    (
        "How do I purge the circuit?",
        "Open the purge valve for 10 seconds, until no bubbles are visible in the transparent "
        "line.",
        "1. EQUIPMENT PREPARATION",
    ),
]


async def purge() -> None:
    """Borra únicamente lo que este script crea.

    El orden importa: mensajes antes que conversaciones, y progreso antes que usuarios, o las
    claves foráneas lo impiden.
    """
    async with AsyncSessionFactory() as session:
        emails = [email for email, *_ in TRAINEES]
        user_ids = list(
            (await session.execute(select(User.id).where(User.email.in_(emails)))).scalars()
        )
        if not user_ids:
            logger.info("No hay actividad sembrada que borrar.")
            return

        conversation_ids = list(
            (
                await session.execute(
                    select(Conversation.id).where(Conversation.user_id.in_(user_ids))
                )
            ).scalars()
        )
        if conversation_ids:
            await session.execute(
                delete(Message).where(Message.conversation_id.in_(conversation_ids))
            )
            await session.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
        await session.execute(
            delete(UserLessonProgress).where(UserLessonProgress.user_id.in_(user_ids))
        )
        await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()
        logger.info(
            "Borrado: %d usuarios, %d conversaciones y su progreso.",
            len(user_ids),
            len(conversation_ids),
        )


async def seed() -> None:
    rng = random.Random(SEED)
    now = datetime.now(UTC)

    async with AsyncSessionFactory() as session:
        machine = (
            (
                await session.execute(
                    select(MachineModel).where(MachineModel.status == PublishStatus.published)
                )
            )
            .scalars()
            .first()
        )
        if machine is None:
            logger.error("No hay ninguna máquina publicada. Ejecuta antes scripts.seed_demo.")
            return

        document = (
            (
                await session.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.machine_model_id == machine.id
                    )
                )
            )
            .scalars()
            .first()
        )

        # --- Usuarios ---------------------------------------------------------
        users: list[User] = []
        for offset, (email, name, specialty, institution) in enumerate(TRAINEES):
            user = (
                (await session.execute(select(User).where(User.email == email))).scalars().first()
            )
            if user is None:
                user = User(
                    email=email,
                    full_name=name,
                    role=UserRole.trainee,
                    hashed_password=hash_password("Demo1234!"),
                    specialty=specialty,
                    institution=institution,
                    # Escalonados para que "usuarios que entraron en la ventana" no sea todo o nada.
                    last_login_at=now - timedelta(days=offset * 3, hours=offset * 5),
                )
                session.add(user)
                await session.flush()
            users.append(user)
        await session.commit()

        already = await session.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id.in_([user.id for user in users]))
        )
        if already:
            logger.info(
                "Ya hay %d conversaciones sembradas. Usa --purge primero si quieres regenerarlas.",
                already,
            )
            return

        # --- Conversaciones y mensajes ---------------------------------------
        # Se distribuyen con un peso creciente hacia el presente: una serie plana se ve
        # fabricada, y una curva ascendente es lo que hace un producto que se está adoptando.
        conversations = 0
        messages = 0
        for day_offset in range(WINDOW_DAYS, 0, -1):
            weekday = (now - timedelta(days=day_offset)).weekday()
            if weekday >= 5 and rng.random() < 0.7:
                continue  # fines de semana casi sin actividad: un hospital tiene calendario

            recency = 1 - (day_offset / WINDOW_DAYS)
            for _ in range(rng.randint(0, 1 + int(recency * 3))):
                user = rng.choice(users)
                question, answer, section = rng.choice(EXCHANGES)
                started = (now - timedelta(days=day_offset)).replace(
                    hour=rng.randint(8, 18), minute=rng.randint(0, 59)
                )

                conversation = Conversation(
                    user_id=user.id,
                    machine_model_id=machine.id,
                    title=question[:80],
                    created_at=started,
                    updated_at=started,
                )
                session.add(conversation)
                await session.flush()
                conversations += 1

                session.add(
                    Message(
                        conversation_id=conversation.id,
                        role=MessageRole.user,
                        content=question,
                        created_at=started,
                        updated_at=started,
                    )
                )
                # Latencias del rango real medido por el smoke test: p50 ~2,3 s, cola a ~4,5 s.
                latency = int(rng.triangular(900, 5200, 2300))
                replied = started + timedelta(milliseconds=latency)
                # Una de cada ocho respuestas sin fuente: es lo que pasa de verdad cuando la
                # pregunta cae fuera del corpus, y un 100 % de grounding sería sospechoso.
                cites = document is not None and rng.random() > 0.125
                session.add(
                    Message(
                        conversation_id=conversation.id,
                        role=MessageRole.assistant,
                        content=answer,
                        sources=(
                            [
                                {
                                    "document_id": str(document.id),
                                    "label": document.title,
                                    "citation": section,
                                    "distance": round(rng.uniform(0.38, 0.62), 4),
                                }
                            ]
                            if cites
                            else []
                        ),
                        provider="openai",
                        model_name="gpt-4o-mini",
                        prompt_tokens=rng.randint(780, 1150),
                        completion_tokens=rng.randint(60, 240),
                        latency_ms=latency,
                        created_at=replied,
                        updated_at=replied,
                    )
                )
                messages += 2
        await session.commit()

        # --- Progreso de lecciones -------------------------------------------
        lessons = list(
            (
                await session.execute(
                    select(Lesson)
                    .join(TrainingModule, TrainingModule.id == Lesson.training_module_id)
                    .where(
                        TrainingModule.machine_model_id == machine.id,
                        Lesson.status == PublishStatus.published,
                        TrainingModule.status == PublishStatus.published,
                    )
                    .order_by(TrainingModule.order_index, Lesson.order_index)
                )
            ).scalars()
        )

        progress_rows = 0
        for index, user in enumerate(users):
            # Cada usuario avanza hasta un punto distinto: así el desglose por estado tiene las
            # tres barras y el porcentaje global no sale ni 0 ni 100.
            reached = min(len(lessons), index + 1)
            for position, lesson in enumerate(lessons[:reached]):
                finished = position < reached - 1
                touched = now - timedelta(days=rng.randint(0, WINDOW_DAYS - 1))
                session.add(
                    UserLessonProgress(
                        user_id=user.id,
                        lesson_id=lesson.id,
                        status=(
                            ProgressStatus.completed if finished else ProgressStatus.in_progress
                        ),
                        watched_percent=100.0 if finished else round(rng.uniform(15, 85), 1),
                        last_position_seconds=round(rng.uniform(20, 220), 1),
                        completed_at=touched if finished else None,
                        created_at=touched,
                        updated_at=touched,
                    )
                )
                progress_rows += 1
        await session.commit()

        logger.info(
            "Sembrado: %d usuarios, %d conversaciones, %d mensajes, %d filas de progreso.",
            len(users),
            conversations,
            messages,
            progress_rows,
        )
        logger.info("Para revertirlo: python -m scripts.seed_demo_activity --purge")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Borra la actividad sembrada y sus usuarios, sin tocar el seed base.",
    )
    args = parser.parse_args()

    try:
        await (purge() if args.purge else seed())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
