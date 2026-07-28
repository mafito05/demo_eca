"""Seed de datos para la demo.

Idempotente: se puede ejecutar varias veces sin duplicar nada. Crea:

- superadmin, admin y el usuario demo (D-003)
- una máquina de urología publicada con su QR
- dos módulos de capacitación con lecciones de texto
- un documento de conocimiento con contenido real para que el agente tenga algo que citar
- un AgentConfig por defecto

Uso (con el stack levantado):
    docker compose exec backend python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionFactory, engine
from app.core.security import hash_password
from app.modules.agent.models import (
    AgentConfig,
    DocumentSourceType,
    KnowledgeDocument,
    LLMProviderKey,
)
from app.modules.auth.models import User, UserRole
from app.modules.lms.models import Lesson, LessonContentType, TrainingModule
from app.modules.machines.models import MachineModel, PublishStatus, Specialty
from app.modules.machines.qr_service import deeplink_url

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")

# El corpus del RAG va en inglés, como el resto del producto (D-039). Conserva los encabezados
# numerados porque el troceado por secciones depende de ellos (D-015).
MANUAL_TEXT = """\
OPERATING MANUAL — URO-LITHO-3000 LITHOTRIPTER

1. EQUIPMENT PREPARATION
1.1 Verify that the unit is connected to a hospital-grade grounded outlet.
1.2 Check the coupling fluid level in the reservoir. The operating range is 1.8 to 2.2 litres.
    Below 1.8 L the unit blocks firing.
1.3 Purge the circuit by opening the purge valve for 10 seconds, until no bubbles are visible
    in the transparent line.

2. DAILY CALIBRATION
2.1 Power on the unit and wait for the self-test (approximately 90 seconds).
2.2 Run routine CAL-01 from the Service > Calibration menu.
2.3 The transducer reference value must fall between 0.95 and 1.05. If it falls outside that
    range, repeat the routine. If it fails again, the transducer requires replacement.

3. OPERATOR SAFETY
3.1 WARNING: do not fire with the therapy head uncoupled. A pulse without coupling medium
    causes irreversible damage to the membrane.
3.2 Wear hearing protection during extended sessions.
3.3 The unit must be disconnected from mains power before any maintenance task.

4. COMMON FAULT RESOLUTION
E-101  Insufficient fluid level. Refill the reservoir and purge.
E-204  Transducer continuity failure. Check the rear connector and repeat CAL-01.
E-330  Over-temperature. Allow 15 minutes of cooling with the unit powered on and the fan
       running; do not power the unit off, as the fan would stop.

5. PREVENTIVE MAINTENANCE
5.1 Coupling fluid replacement: every 300 shots or 30 days, whichever comes first.
5.2 Therapy head membrane inspection: every 1,000 shots.
5.3 Every intervention must be recorded in the unit's service logbook.
"""


async def seed() -> None:
    async with AsyncSessionFactory() as session:
        # --- Usuarios --------------------------------------------------------
        users = [
            (
                "superadmin@demoeca.example.com",
                "Super Administrator",
                UserRole.superadmin,
                "Demo1234!",
            ),
            (
                "admin@demoeca.example.com",
                "Content Administrator",
                UserRole.admin,
                "Demo1234!",
            ),
        ]
        for email, name, role, password in users:
            existing = await session.execute(select(User).where(User.email == email))
            if existing.scalars().first() is None:
                session.add(
                    User(
                        email=email,
                        full_name=name,
                        role=role,
                        hashed_password=hash_password(password),
                    )
                )
                logger.info("Usuario creado: %s / %s", email, password)

        demo = await session.execute(select(User).where(User.email == settings.DEMO_USER_EMAIL))
        if demo.scalars().first() is None:
            session.add(
                User(
                    email=settings.DEMO_USER_EMAIL,
                    full_name="Dr. Demo User",
                    role=UserRole.trainee,
                    is_demo=True,
                    specialty="Urology",
                    institution="Demo Hospital",
                )
            )
            logger.info(
                "Usuario demo creado: %s (entra por /auth/demo-login)", settings.DEMO_USER_EMAIL
            )
        await session.commit()

        # --- Máquina ---------------------------------------------------------
        result = await session.execute(
            select(MachineModel).where(MachineModel.code == "URO-LITHO-3000")
        )
        machine = result.scalars().first()
        if machine is None:
            machine = MachineModel(
                code="URO-LITHO-3000",
                name="Uro-Litho 3000 Lithotripter",
                manufacturer="Demo MedTech",
                specialty=Specialty.urologia,
                description=(
                    "Extracorporeal shock wave lithotripter for the treatment of renal "
                    "and ureteral stones."
                ),
                status=PublishStatus.published,
            )
            session.add(machine)
            await session.commit()
            logger.info("Máquina creada. QR -> %s", deeplink_url(machine.qr_token))
        else:
            logger.info("Máquina existente. QR -> %s", deeplink_url(machine.qr_token))

        # --- Módulos y lecciones ---------------------------------------------
        existing_modules = await session.execute(
            select(TrainingModule).where(TrainingModule.machine_model_id == machine.id)
        )
        if not list(existing_modules.scalars()):
            plan = [
                (
                    "Preparation and start-up",
                    ["Connection and pre-use checks", "Purging the coupling circuit"],
                ),
                (
                    "Calibration and maintenance",
                    ["CAL-01 calibration routine", "Preventive maintenance and logging"],
                ),
            ]
            for module_index, (module_title, lesson_titles) in enumerate(plan):
                module = TrainingModule(
                    machine_model_id=machine.id,
                    title=module_title,
                    order_index=module_index,
                    status=PublishStatus.published,
                    requires_previous=module_index > 0,
                )
                session.add(module)
                await session.commit()

                for lesson_index, lesson_title in enumerate(lesson_titles):
                    session.add(
                        Lesson(
                            training_module_id=module.id,
                            title=lesson_title,
                            content_type=LessonContentType.text,
                            order_index=lesson_index,
                            body=f"Content pending upload for: {lesson_title}.",
                            estimated_minutes=8,
                            status=PublishStatus.published,
                        )
                    )
            await session.commit()
            logger.info("2 módulos con 4 lecciones creados.")

        # --- Conocimiento para el RAG ----------------------------------------
        existing_doc = await session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.machine_model_id == machine.id,
                KnowledgeDocument.title == "URO-LITHO-3000 Operating Manual",
            )
        )
        if existing_doc.scalars().first() is None:
            session.add(
                KnowledgeDocument(
                    title="URO-LITHO-3000 Operating Manual",
                    source_type=DocumentSourceType.raw_text,
                    machine_model_id=machine.id,
                    raw_text=MANUAL_TEXT,
                )
            )
            await session.commit()
            logger.info(
                "Documento de conocimiento creado. Para vectorizarlo: "
                "POST /api/v1/agent/documents/{id}/reindex (requiere EMBEDDING_API_KEY)."
            )

        # --- Agente por defecto ----------------------------------------------
        existing_agent = await session.execute(
            select(AgentConfig).where(AgentConfig.is_default.is_(True))
        )
        existing_config = existing_agent.scalars().first()
        if existing_config is not None and not existing_config.suggested_questions:
            # Backfill idempotente: los configs creados antes de D-053 no tienen preguntas
            # sugeridas y la app mostraría las genéricas en lugar de las del manual sembrado.
            existing_config.suggested_questions = [
                "What should I do if the unit shows error E-204?",
                "How often does the coupling fluid need changing?",
                "What is the valid transducer range after calibration?",
            ]
            session.add(existing_config)
            await session.commit()
            logger.info("Preguntas sugeridas añadidas al AgentConfig existente.")
        if existing_config is None:
            session.add(
                AgentConfig(
                    name="General technical assistant",
                    description="Default agent for all equipment.",
                    provider=LLMProviderKey.anthropic,
                    model_name="claude-sonnet-5",
                    temperature=0.2,
                    max_tokens=1024,
                    rag_enabled=True,
                    tools_enabled=False,
                    is_default=True,
                    # Preguntas que el manual sembrado puede responder de verdad: la primera
                    # impresión del chat no debe ser una pregunta que acabe en "no está en la
                    # documentación". Editables desde el panel (D-053).
                    suggested_questions=[
                        "What should I do if the unit shows error E-204?",
                        "How often does the coupling fluid need changing?",
                        "What is the valid transducer range after calibration?",
                    ],
                )
            )
            await session.commit()
            logger.info(
                "AgentConfig por defecto creado (Anthropic). Falta registrar la credencial "
                "en POST /api/v1/agent/credentials."
            )

    await engine.dispose()
    logger.info("Seed completado.")


if __name__ == "__main__":
    asyncio.run(seed())
