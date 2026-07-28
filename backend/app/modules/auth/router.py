"""Autenticación: login real, refresh y el bypass de demostración (D-003)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select

from app.core.base import utcnow
from app.core.config import settings
from app.core.deps import CurrentUser, SessionDep, require_superadmin
from app.core.security import TokenType, create_token, decode_token, hash_password, verify_password
from app.modules.auth import schemas
from app.modules.auth.models import User, UserRole

router = APIRouter()

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password.",
)


def _issue_tokens(user: User) -> schemas.TokenPair:
    # El rol viaja en el token para que el cliente pinte la UI sin una llamada extra. La
    # autorización del servidor NO se basa en ese claim: se relee de la BD en cada request,
    # porque un rol revocado no debe seguir siendo válido hasta que expire el token.
    claims = {"role": user.role.value, "email": user.email}
    return schemas.TokenPair(
        access_token=create_token(user.id, TokenType.access, claims),
        refresh_token=create_token(user.id, TokenType.refresh),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=schemas.TokenPair)
async def login(payload: schemas.LoginRequest, session: SessionDep) -> schemas.TokenPair:
    result = await session.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalars().first()

    # Se verifica la contraseña aunque el usuario no exista para no filtrar por tiempo de
    # respuesta qué emails están registrados.
    stored_hash = user.hashed_password if user and user.hashed_password else "$2b$12$" + "x" * 53
    password_ok = verify_password(payload.password, stored_hash)

    if user is None or not user.is_active or not user.hashed_password or not password_ok:
        raise _INVALID_CREDENTIALS

    user.last_login_at = utcnow()
    session.add(user)
    await session.commit()
    return _issue_tokens(user)


@router.post(
    "/demo-login",
    response_model=schemas.TokenPair,
    summary="Demo login bypass",
    description=(
        "Returns a valid token for the shared demo user, so the app can scan a QR code "
        "and go straight in. Controlled by AUTH_BYPASS_ENABLED."
    ),
)
async def demo_login(session: SessionDep) -> schemas.TokenPair:
    # 404 y no 403: con el flag desactivado, el endpoint no existe. No anunciamos la puerta.
    if not settings.AUTH_BYPASS_ENABLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")

    result = await session.execute(select(User).where(User.email == settings.DEMO_USER_EMAIL))
    user = result.scalars().first()

    # Autoprovisión: la demo debe arrancar sin depender de que alguien ejecutase el seed.
    if user is None:
        user = User(
            email=settings.DEMO_USER_EMAIL,
            full_name="Usuario Demo",
            role=UserRole.trainee,
            is_demo=True,
            hashed_password=None,
        )
        session.add(user)
        await session.commit()

    user.last_login_at = utcnow()
    session.add(user)
    await session.commit()
    return _issue_tokens(user)


@router.post("/refresh", response_model=schemas.TokenPair)
async def refresh(payload: schemas.RefreshRequest, session: SessionDep) -> schemas.TokenPair:
    try:
        claims = decode_token(payload.refresh_token, TokenType.refresh)
        user = await session.get(User, uuid.UUID(claims["sub"]))
    except (InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.") from None

    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.")
    return _issue_tokens(user)


@router.get("/me", response_model=schemas.UserRead)
async def me(user: CurrentUser) -> User:
    return user


@router.get(
    "/users",
    response_model=list[schemas.UserRead],
    dependencies=[Depends(require_superadmin)],
)
async def list_users(session: SessionDep) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars())


@router.post(
    "/users",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
)
async def create_user(payload: schemas.UserCreate, session: SessionDep) -> User:
    existing = await session.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered.")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        specialty=payload.specialty,
        institution=payload.institution,
    )
    session.add(user)
    await session.commit()
    return user


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_superadmin)],
    summary="Delete a user and their personal data",
)
async def delete_user(user_id: uuid.UUID, session: SessionDep, current: CurrentUser) -> None:
    """Borrado real, no desactivación.

    Existe porque el derecho de supresión sobre datos personales lo exige: un profesional que
    deja la organización puede pedir que se borre su historial de capacitación, y no basta con
    marcarlo inactivo.

    El borrado en cascada es explícito y no delegado a `ON DELETE CASCADE` de la base de datos,
    porque las tablas no se tratan igual:

    - Progreso, intentos, respuestas, certificados y conversaciones **se borran**: son datos de
      la persona.
    - `tool_invocations` **se anonimiza** (`user_id = NULL`) en lugar de borrarse. Es la
      auditoría de lo que el agente ejecutó contra sistemas externos; eliminar esas filas
      dejaría huecos en un registro de seguridad. La fila se conserva, la identidad no.
    """
    from sqlalchemy import delete, update

    from app.modules.agent.models import Conversation, Message, ToolInvocation
    from app.modules.assessments.models import AttemptAnswer, Certificate, QuizAttempt
    from app.modules.lms.models import UserLessonProgress

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    # Un superadmin que se borra a sí mismo deja el sistema sin administrador.
    if user.id == current.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot delete your own user.")

    # El usuario demo lo autoprovisiona el bypass; borrarlo con el flag activo solo lo recrearía.
    if user.is_demo:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The demo user cannot be deleted; disable AUTH_BYPASS_ENABLED instead.",
        )

    attempts = select(QuizAttempt.id).where(QuizAttempt.user_id == user_id)
    conversations = select(Conversation.id).where(Conversation.user_id == user_id)

    await session.execute(delete(AttemptAnswer).where(AttemptAnswer.attempt_id.in_(attempts)))
    await session.execute(delete(Certificate).where(Certificate.user_id == user_id))
    await session.execute(delete(QuizAttempt).where(QuizAttempt.user_id == user_id))
    await session.execute(delete(UserLessonProgress).where(UserLessonProgress.user_id == user_id))
    await session.execute(delete(Message).where(Message.conversation_id.in_(conversations)))
    await session.execute(
        update(ToolInvocation).where(ToolInvocation.user_id == user_id).values(user_id=None)
    )
    await session.execute(delete(Conversation).where(Conversation.user_id == user_id))

    await session.delete(user)
    await session.commit()
