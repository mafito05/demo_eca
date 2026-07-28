"""Elimina los usuarios QA que quedaron de ejecuciones antiguas del test de video.

    docker compose exec backend python -m scripts.cleanup_qa_users

El test de video ahora se limpia solo, pero las ejecuciones anteriores a ese arreglo dejaron
usuarios `qa-video-*` en la base de datos. Este script los barre de una vez.

Reutiliza la misma cascada explícita que el endpoint de borrado, en lugar de hacer un DELETE a
saco: así no hay dos definiciones de "qué implica borrar un usuario" que puedan divergir.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import delete, select, update

from app.core.database import AsyncSessionFactory, engine
from app.models import *  # noqa: F403
from app.modules.agent.models import Conversation, Message, ToolInvocation
from app.modules.assessments.models import AttemptAnswer, Certificate, QuizAttempt
from app.modules.auth.models import User
from app.modules.lms.models import UserLessonProgress

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cleanup")

PATTERN = "qa-video-%"


async def main() -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.email.like(PATTERN)))
        users = list(result.scalars())

        if not users:
            logger.info("No hay usuarios QA que limpiar.")
            await engine.dispose()
            return

        for user in users:
            attempts = select(QuizAttempt.id).where(QuizAttempt.user_id == user.id)
            conversations = select(Conversation.id).where(Conversation.user_id == user.id)

            await session.execute(
                delete(AttemptAnswer).where(AttemptAnswer.attempt_id.in_(attempts))
            )
            await session.execute(delete(Certificate).where(Certificate.user_id == user.id))
            await session.execute(delete(QuizAttempt).where(QuizAttempt.user_id == user.id))
            await session.execute(
                delete(UserLessonProgress).where(UserLessonProgress.user_id == user.id)
            )
            await session.execute(delete(Message).where(Message.conversation_id.in_(conversations)))
            # La auditoría de tools se anonimiza, no se borra (ver el endpoint de borrado).
            await session.execute(
                update(ToolInvocation).where(ToolInvocation.user_id == user.id).values(user_id=None)
            )
            await session.execute(delete(Conversation).where(Conversation.user_id == user.id))
            await session.delete(user)
            logger.info("Eliminado %s", user.email)

        await session.commit()
        logger.info("%d usuarios QA eliminados.", len(users))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
