"""Dependências compartilhadas pelas rotas.

A autenticação usa um cookie httpOnly com um token de sessão (ver `app.api.v1.auth`).
Rotas que exigem login declaram `AuthDep` (ou `UserDep`); as demais continuam públicas.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import hash_token
from app.db.models import User, UserSession
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


async def get_optional_auth(request: Request, db: SessionDep) -> AuthContext | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    row = await db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    return AuthContext(user=row.user, session=row) if row else None


OptionalAuthDep = Annotated[AuthContext | None, Depends(get_optional_auth)]


async def require_auth(auth: OptionalAuthDep) -> AuthContext:
    if auth is None:
        raise UnauthorizedError("Sua sessão expirou. Entre novamente.")
    return auth


AuthDep = Annotated[AuthContext, Depends(require_auth)]


async def require_user(auth: AuthDep) -> User:
    return auth.user


UserDep = Annotated[User, Depends(require_user)]
