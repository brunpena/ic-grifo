"""Dependências compartilhadas pelas rotas.

A autenticação usa um cookie httpOnly com um token de sessão (ver `app.api.v1.auth`).
Rotas que exigem login declaram `AuthDep` (ou `UserDep`); as demais continuam públicas.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import make_transient_to_detached

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.request_metrics import set_user
from app.core.security import hash_token
from app.db.models import User, UserSession
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


# ----- cache das sessões validadas -----
# Toda rota logada consultava o banco para validar o cookie (~200 ms no Supabase). Uma
# sessão já validada é reaproveitada por `AUTH_CACHE_SECONDS`. O cache é por processo:
# logout, troca de senha e edição do perfil o limpam aqui; em outro worker, a mudança
# vale no máximo depois desse prazo.


@dataclass(frozen=True)
class _CachedAuth:
    user: User  # cópia desanexada, só para leitura
    session_id: uuid.UUID
    user_id: uuid.UUID
    session_expires_at: datetime
    cached_until: float


_auth_cache: dict[str, _CachedAuth] = {}


def _detached_copy[T](obj: T) -> T:
    """Cópia com os valores das colunas, reconhecida como linha existente pelo `merge`."""
    mapper = inspect(type(obj))
    copy = type(obj)(**{c.key: getattr(obj, c.key) for c in mapper.column_attrs})
    make_transient_to_detached(copy)
    return copy


def forget_user_sessions(user_id: uuid.UUID) -> None:
    """Descarta as sessões em cache de um usuário (logout, senha ou perfil alterados)."""
    for key, entry in list(_auth_cache.items()):
        if entry.user_id == user_id:
            _auth_cache.pop(key, None)


def clear_auth_cache() -> None:
    _auth_cache.clear()


async def _from_cache(db: AsyncSession, token_hash: str) -> AuthContext | None:
    entry = _auth_cache.get(token_hash)
    if entry is None:
        return None
    if entry.cached_until <= time.monotonic() or entry.session_expires_at <= datetime.now(UTC):
        _auth_cache.pop(token_hash, None)
        return None
    # `load=False` anexa a cópia à sessão da requisição sem consultar o banco; alterações
    # feitas pela rota (ex.: perfil) são gravadas normalmente no commit.
    user = await db.merge(_detached_copy(entry.user), load=False)
    session = UserSession(
        id=entry.session_id, user_id=entry.user_id, expires_at=entry.session_expires_at
    )
    return AuthContext(user=user, session=session)


async def get_optional_auth(request: Request, db: SessionDep) -> AuthContext | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    token_hash = hash_token(token)
    if settings.auth_cache_seconds and (cached := await _from_cache(db, token_hash)):
        set_user(cached.user.id)
        return cached
    row = await db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    if row is None:
        return None
    if settings.auth_cache_seconds:
        _auth_cache[token_hash] = _CachedAuth(
            user=_detached_copy(row.user),
            session_id=row.id,
            user_id=row.user_id,
            session_expires_at=row.expires_at,
            cached_until=time.monotonic() + settings.auth_cache_seconds,
        )
    set_user(row.user_id)
    return AuthContext(user=row.user, session=row)


OptionalAuthDep = Annotated[AuthContext | None, Depends(get_optional_auth)]


async def require_auth(auth: OptionalAuthDep) -> AuthContext:
    if auth is None:
        raise UnauthorizedError("Sua sessão expirou. Entre novamente.")
    return auth


AuthDep = Annotated[AuthContext, Depends(require_auth)]


async def require_user(auth: AuthDep) -> User:
    return auth.user


UserDep = Annotated[User, Depends(require_user)]
