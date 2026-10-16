"""Cadastro, login, logout e perfil do usuário."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, select

from app.api.deps import AuthDep, OptionalAuthDep, SessionDep, UserDep
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, UnauthorizedError
from app.core.security import hash_password, hash_token, new_session_token, verify_password
from app.db.models import User, UserSession
from app.schemas.auth import LoginIn, PasswordChangeIn, ProfileUpdateIn, RegisterIn, UserOut
from app.schemas.common import error_responses

router = APIRouter(tags=["autenticação"])

# Usado quando o e-mail não existe, para o tempo de resposta não revelar quais contas existem.
_DUMMY_HASH = hash_password("senha-que-nao-existe")


async def _start_session(db: SessionDep, user: User, response: Response) -> None:
    settings = get_settings()
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
        )
    )
    await db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


async def _email_taken(db: SessionDep, email: str) -> bool:
    return await db.scalar(select(User.id).where(User.email == email)) is not None


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma conta e já inicia a sessão",
    responses=error_responses(409, 422),
)
async def register(body: RegisterIn, db: SessionDep, response: Response) -> UserOut:
    if await _email_taken(db, body.email):
        raise ConflictError("Já existe uma conta com este e-mail.")
    user = User(
        name=body.name,
        email=body.email,
        password_hash=await asyncio.to_thread(hash_password, body.password),
    )
    db.add(user)
    await db.flush()
    await _start_session(db, user, response)
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/auth/login", summary="Entra com e-mail e senha", responses=error_responses(401, 422))
async def login(body: LoginIn, db: SessionDep, response: Response) -> UserOut:
    user = await db.scalar(select(User).where(User.email == body.email))
    stored = user.password_hash if user else _DUMMY_HASH
    valid = await asyncio.to_thread(verify_password, body.password, stored)
    if not user or not valid:
        raise UnauthorizedError("E-mail ou senha incorretos.", code="invalid_credentials")
    await _start_session(db, user, response)
    return UserOut.model_validate(user)


@router.post(
    "/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Encerra a sessão atual"
)
async def logout(auth: OptionalAuthDep, db: SessionDep, response: Response) -> None:
    if auth:
        await db.execute(delete(UserSession).where(UserSession.id == auth.session.id))
        await db.commit()
    _clear_cookie(response)


@router.get("/auth/me", summary="Usuário da sessão atual", responses=error_responses(401))
async def me(user: UserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", summary="Atualiza o perfil", responses=error_responses(401, 409, 422))
async def update_profile(body: ProfileUpdateIn, user: UserDep, db: SessionDep) -> UserOut:
    changes = body.model_dump(exclude_unset=True)
    # Nome e e-mail são obrigatórios: `null` é tratado como "não mudar".
    for required in ("name", "email"):
        if changes.get(required) is None:
            changes.pop(required, None)
    new_email = changes.get("email")
    if new_email and new_email != user.email and await _email_taken(db, new_email):
        raise ConflictError("Já existe uma conta com este e-mail.")
    for field, value in changes.items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Troca a senha e encerra as outras sessões",
    responses=error_responses(400, 401, 422),
)
async def change_password(body: PasswordChangeIn, auth: AuthDep, db: SessionDep) -> None:
    user = auth.user
    if not await asyncio.to_thread(verify_password, body.current_password, user.password_hash):
        raise AppError("A senha atual está incorreta.", code="wrong_password")
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != auth.session.id)
    )
    await db.commit()
