"""Seed de datos para la demo.

Idempotente: se puede ejecutar varias veces sin duplicar nada. Crea:

- superadmin, admin y el usuario demo (D-003)
- dos máquinas de urología publicadas con su QR (litotriptor y uroflujómetro)
- el temario de cada una: dos módulos con lecciones
- un manual por equipo, con contenido real para que el agente tenga algo que citar
- un AgentConfig por defecto

Uso (con el stack levantado):
    docker compose exec backend python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple

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

# Manual del segundo equipo. Misma forma que el anterior —encabezados numerados, secciones
# equivalentes— porque el troceado del RAG parte por ellos (D-015).
#
# Los códigos de fallo son `UF-xxx` y no `E-xxx` a propósito: al no colisionar con los del
# litotriptor, sirven para comprobar que la recuperación **discrimina por equipo** en lugar de
# mezclar los dos corpus, algo que con un solo manual sembrado no se podía verificar.
#
# Sin una sola afirmación clínica: el guardrail de D-006 debe seguir rehusando ese terreno, y el
# corpus no debe tentarlo con valores de referencia de pacientes.
UROFLOW_MANUAL_TEXT = """\
OPERATING MANUAL — URO-FLOW-2000 UROFLOWMETER

1. EQUIPMENT PREPARATION
1.1 Place the unit on a level, vibration-free floor. The bubble indicator on the base must be
    centred; a tilt above 2 degrees invalidates the gravimetric measurement.
1.2 Connect the load cell cable to the rear PORT A connector and confirm that the green status
    LED is steady. A blinking LED means the cell is not recognised.
1.3 Fit a clean collection funnel and place an empty 1,000 mL beaker on the platform. The beaker
    must be dry: residual liquid is counted as voided volume.
1.4 Allow 15 minutes of warm-up before the first study of the day. The load cell drifts while the
    electronics reach thermal equilibrium.

2. DAILY CALIBRATION
2.1 Run routine FLOW-CAL from the Service > Calibration menu.
2.2 Pour exactly 500 mL of water at 20 +/- 2 degrees Celsius into the funnel at a steady rate.
2.3 The unit must report a volume between 485 and 515 mL, that is a tolerance of +/- 3 percent,
    and a zero drift below 2 g over 60 seconds.
2.4 Nominal ranges of the unit: flow rate 0 to 50 mL/s, volume 0 to 1,000 mL, acquisition at
    10 Hz, printed resolution 0.1 mL/s.
2.5 The parameters recorded by each study are maximum flow rate, average flow rate, voided volume,
    flow time and time to maximum flow. The unit records them; it does not interpret them.
2.6 If the reported volume falls outside tolerance twice in a row, the load cell must be replaced.
    Do not compensate the reading with a manual offset in the service menu.

3. OPERATOR SAFETY AND HYGIENE
3.1 The funnel and the beaker are single-patient items. Discard them or run the validated
    disinfection cycle after every study.
3.2 WARNING: never rinse the unit under running water. The load cell housing is not sealed and
    liquid ingress destroys the transducer.
3.3 Clean external surfaces with a 70 percent isopropyl alcohol wipe. Chlorine-based products
    permanently cloud the display window.
3.4 Disconnect the unit from mains power before removing any cover or replacing the printer.

4. COMMON FAULT RESOLUTION
UF-101  Load cell zero drift out of range. Remove every load from the funnel, wait 30 seconds and
        repeat FLOW-CAL.
UF-207  Overflow detected: volume above 1,000 mL or liquid outside the beaker. Empty the beaker
        and repeat the study. The recorded curve is discarded and cannot be recovered.
UF-315  Unstable signal from the load cell. Check the PORT A connector and move the unit away from
        vibration sources such as air-conditioning ducts or centrifuges.
UF-402  Thermal printer out of paper or cover open. Load a 58 mm roll and close the cover; the
        pending report is reprinted automatically.
UF-509  Internal clock lost after a power failure. Set date and time before exporting, or the
        study is filed under the wrong session.

5. PREVENTIVE MAINTENANCE
5.1 FLOW-CAL calibration check: every day, before the first study.
5.2 Full load cell verification with a certified 500 g weight: every 90 days.
5.3 Funnel and drain tube replacement: every 500 studies or 12 months, whichever comes first.
5.4 Thermal printer head cleaning: every 20 paper rolls.
5.5 Every intervention must be recorded in the unit's service logbook.
"""


class LessonSpec(NamedTuple):
    """Una lección del plan de un equipo.

    Existe para poder expresar la lección de video en borrador sin repetir los valores por
    defecto en cada una de las que sí son de texto.
    """

    title: str
    content_type: LessonContentType = LessonContentType.text
    status: PublishStatus = PublishStatus.published
    minutes: int = 8


async def _ensure_machine(
    session,
    *,
    code: str,
    name: str,
    description: str,
    manufacturer: str = "Demo MedTech",
    specialty: Specialty = Specialty.urologia,
) -> MachineModel:
    """Crea la máquina si no existe. La guarda es el `code`, que es único."""
    machine = (
        (await session.execute(select(MachineModel).where(MachineModel.code == code)))
        .scalars()
        .first()
    )
    if machine is None:
        machine = MachineModel(
            code=code,
            name=name,
            manufacturer=manufacturer,
            specialty=specialty,
            description=description,
            status=PublishStatus.published,
        )
        session.add(machine)
        await session.commit()
        await session.refresh(machine)
        logger.info("Máquina %s creada. QR -> %s", code, deeplink_url(machine.qr_token))
    else:
        logger.info("Máquina %s existente. QR -> %s", code, deeplink_url(machine.qr_token))
    return machine


async def _ensure_modules(
    session, machine: MachineModel, plan: list[tuple[str, list[LessonSpec]]]
) -> None:
    """Crea el temario si la máquina no tiene ningún módulo todavía.

    La guarda es "no tiene módulos" y no "no tiene este módulo": así una reejecución no pisa un
    temario que el admin haya editado desde el panel.
    """
    existing = await session.execute(
        select(TrainingModule).where(TrainingModule.machine_model_id == machine.id)
    )
    if list(existing.scalars()):
        return

    for module_index, (module_title, lessons) in enumerate(plan):
        module = TrainingModule(
            machine_model_id=machine.id,
            title=module_title,
            order_index=module_index,
            status=PublishStatus.published,
            requires_previous=module_index > 0,
        )
        session.add(module)
        await session.commit()
        await session.refresh(module)

        for lesson_index, spec in enumerate(lessons):
            session.add(
                Lesson(
                    training_module_id=module.id,
                    title=spec.title,
                    content_type=spec.content_type,
                    order_index=lesson_index,
                    # Las de video no llevan `body`: su contenido es el asset que se adjunte.
                    body=(
                        f"Content pending upload for: {spec.title}."
                        if spec.content_type is LessonContentType.text
                        else None
                    ),
                    estimated_minutes=spec.minutes,
                    status=spec.status,
                )
            )
    await session.commit()
    total = sum(len(lessons) for _, lessons in plan)
    logger.info("%s: %d módulos con %d lecciones creados.", machine.code, len(plan), total)


async def _ensure_document(session, machine: MachineModel, *, title: str, text: str) -> None:
    existing = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.machine_model_id == machine.id,
            KnowledgeDocument.title == title,
        )
    )
    if existing.scalars().first() is not None:
        return

    session.add(
        KnowledgeDocument(
            title=title,
            source_type=DocumentSourceType.raw_text,
            machine_model_id=machine.id,
            raw_text=text,
        )
    )
    await session.commit()
    logger.info(
        "Documento '%s' creado. Para vectorizarlo: "
        "POST /api/v1/agent/documents/{id}/reindex (requiere EMBEDDING_API_KEY).",
        title,
    )


async def _ensure_machine_agent(
    session, machine: MachineModel, *, name: str, questions: list[str]
) -> None:
    """AgentConfig propio del equipo, con preguntas que su manual puede responder.

    `resolve_config` prefiere el config de la máquina sobre el marcado por defecto. Sin esto, al
    abrir el chat del uroflujómetro la app ofrecería las preguntas del litotriptor —el fluido de
    acoplamiento, el error E-204— que acabarían en "no está en la documentación": justo el fallo
    que D-053 vino a corregir.
    """
    existing = await session.execute(
        select(AgentConfig).where(AgentConfig.machine_model_id == machine.id)
    )
    if existing.scalars().first() is not None:
        return

    session.add(
        AgentConfig(
            name=name,
            description=f"Agent scoped to {machine.code}.",
            machine_model_id=machine.id,
            provider=LLMProviderKey.openai,
            model_name="gpt-4o-mini",
            temperature=0.2,
            max_tokens=1024,
            rag_enabled=True,
            tools_enabled=False,
            is_default=False,
            suggested_questions=questions,
        )
    )
    await session.commit()
    logger.info("AgentConfig propio de %s creado.", machine.code)


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

        # --- Equipo 1: litotriptor ------------------------------------------
        machine = await _ensure_machine(
            session,
            code="URO-LITHO-3000",
            name="Uro-Litho 3000 Lithotripter",
            description=(
                "Extracorporeal shock wave lithotripter for the treatment of renal "
                "and ureteral stones."
            ),
        )
        await _ensure_modules(
            session,
            machine,
            [
                (
                    "Preparation and start-up",
                    [
                        LessonSpec("Connection and pre-use checks"),
                        LessonSpec("Purging the coupling circuit"),
                    ],
                ),
                (
                    "Calibration and maintenance",
                    [
                        LessonSpec("CAL-01 calibration routine"),
                        LessonSpec("Preventive maintenance and logging"),
                    ],
                ),
            ],
        )
        await _ensure_document(
            session, machine, title="URO-LITHO-3000 Operating Manual", text=MANUAL_TEXT
        )

        # --- Equipo 2: uroflujómetro ----------------------------------------
        uroflow = await _ensure_machine(
            session,
            code="URO-FLOW-2000",
            name="Uro-Flow 2000 Uroflowmeter",
            description=(
                "Gravimetric uroflowmeter for non-invasive recording of urinary flow rate "
                "and voided volume."
            ),
        )
        await _ensure_modules(
            session,
            uroflow,
            [
                (
                    "Preparation and calibration",
                    [
                        LessonSpec("Levelling, load cell and funnel setup", minutes=7),
                        LessonSpec("FLOW-CAL daily calibration", minutes=10),
                    ],
                ),
                (
                    "Studies and reporting",
                    [
                        # Hueco reservado para el video que subirá el cliente. Va en BORRADOR a
                        # propósito: una lección de tipo `video` publicada sin asset le enseña al
                        # trainee un reproductor que no arranca. En draft es invisible hasta que se
                        # adjunta el video y se publica desde el panel con un clic.
                        LessonSpec(
                            "Running a uroflowmetry study",
                            content_type=LessonContentType.video,
                            status=PublishStatus.draft,
                            minutes=12,
                        ),
                        LessonSpec("Report export and fault codes", minutes=6),
                    ],
                ),
            ],
        )
        await _ensure_document(
            session, uroflow, title="URO-FLOW-2000 Operating Manual", text=UROFLOW_MANUAL_TEXT
        )
        await _ensure_machine_agent(
            session,
            uroflow,
            name="Uroflowmeter technical assistant",
            questions=[
                "What does error UF-207 mean?",
                "How much water does the FLOW-CAL routine need, and at what temperature?",
                "How often must the load cell be verified?",
            ],
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
