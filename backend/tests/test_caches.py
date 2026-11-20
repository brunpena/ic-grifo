"""Caches que evitam idas ao Supabase: sessões validadas e cópia local dos PDFs."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api import deps
from app.core.config import get_settings
from app.core.security import hash_token
from app.db.models import User, UserSession
from app.db.session import engine
from app.processing.shared import storage

TOKEN = "token-de-teste"


def _request() -> Request:
    cookie = f"{get_settings().session_cookie_name}={TOKEN}".encode()
    return Request({"type": "http", "headers": [(b"cookie", cookie)]})


class FakeDb:
    """Conta as consultas; `merge` usa uma sessão real, que não consulta com load=False."""

    def __init__(self, row: UserSession | None):
        self.row = row
        self.queries = 0
        self.real = AsyncSession(engine)

    async def scalar(self, _statement):
        self.queries += 1
        return self.row

    async def merge(self, obj, load=True):
        return await self.real.merge(obj, load=load)


def _row(expires_in=timedelta(days=1)) -> UserSession:
    user = User(id=uuid.uuid4(), name="Ana", email="ana@exemplo.com", password_hash="x")
    return UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        user=user,
        token_hash=hash_token(TOKEN),
        expires_at=datetime.now(UTC) + expires_in,
    )


@pytest.fixture(autouse=True)
def _clean_auth_cache(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_cache_seconds", 60)
    deps.clear_auth_cache()
    yield
    deps.clear_auth_cache()


async def test_validated_session_is_reused_without_query():
    db = FakeDb(_row())
    first = await deps.get_optional_auth(_request(), db)
    second = await deps.get_optional_auth(_request(), db)
    assert db.queries == 1
    assert second.user.id == first.user.id and second.session.id == first.session.id
    # A cópia fica anexada à sessão da requisição: a rota pode alterá-la e gravar.
    assert second.user in db.real
    await db.real.close()


async def test_forget_user_sessions_forces_new_lookup():
    db = FakeDb(_row())
    auth = await deps.get_optional_auth(_request(), db)
    deps.forget_user_sessions(auth.user.id)
    db.row = None  # sessão apagada no banco (logout ou troca de senha)
    assert await deps.get_optional_auth(_request(), db) is None
    assert db.queries == 2
    await db.real.close()


async def test_cache_respects_ttl_and_session_expiry(monkeypatch):
    db = FakeDb(_row())
    await deps.get_optional_auth(_request(), db)
    entry = deps._auth_cache[hash_token(TOKEN)]
    deps._auth_cache[hash_token(TOKEN)] = entry.__class__(
        **{**entry.__dict__, "session_expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    db.row = None
    assert await deps.get_optional_auth(_request(), db) is None
    assert db.queries == 2
    await db.real.close()


async def test_auth_cache_can_be_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_cache_seconds", 0)
    db = FakeDb(_row())
    await deps.get_optional_auth(_request(), db)
    await deps.get_optional_auth(_request(), db)
    assert db.queries == 2
    assert not deps._auth_cache
    await db.real.close()


# ----- PDFs -----


@pytest.fixture
def supabase_storage(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "pdf_cache_dir", tmp_path)
    monkeypatch.setattr(settings, "pdf_cache_max_mb", 1)
    remote: dict[str, bytes] = {}
    calls = {"read": 0}

    async def save_file(name, data, content_type):
        remote[name] = data
        return f"supabase:documents/{name}"

    async def read_file(name):
        calls["read"] += 1
        return remote[name]

    async def delete_files(names):
        for name in names:
            remote.pop(name, None)

    monkeypatch.setattr(storage, "save_file", save_file)
    monkeypatch.setattr(storage, "read_file", read_file)
    monkeypatch.setattr(storage, "delete_files", delete_files)
    return remote, calls, tmp_path


async def test_saved_pdf_is_read_from_disk(supabase_storage):
    remote, calls, folder = supabase_storage
    document_id = uuid.uuid4()
    await storage.save_pdf(document_id, b"%PDF-1")
    assert await storage.read_pdf(document_id) == b"%PDF-1"
    assert calls["read"] == 0
    await storage.delete_pdf(document_id)
    assert not list(folder.glob("*.pdf")) and not remote


async def test_downloaded_pdf_is_kept_for_next_read(supabase_storage):
    remote, calls, _ = supabase_storage
    document_id = uuid.uuid4()
    remote[storage.pdf_name(document_id)] = b"%PDF-2"
    assert await storage.read_pdf(document_id) == b"%PDF-2"
    assert await storage.read_pdf(document_id) == b"%PDF-2"
    assert calls["read"] == 1


async def test_pdf_cache_drops_oldest_over_limit(supabase_storage):
    _, _, folder = supabase_storage
    big = b"x" * (600 * 1024)  # dois arquivos passam do limite de 1 MB
    first, second = uuid.uuid4(), uuid.uuid4()
    await storage.save_pdf(first, big)
    old = datetime.now().timestamp() - 3600  # o primeiro é o menos usado
    os.utime(folder / storage.pdf_name(first), (old, old))
    await storage.save_pdf(second, big)
    assert [p.name for p in folder.glob("*.pdf")] == [storage.pdf_name(second)]


async def test_local_backend_skips_pdf_cache(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "pdf_cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "local_storage_dir", tmp_path / "storage")
    document_id = uuid.uuid4()
    await storage.save_pdf(document_id, b"%PDF-3")
    assert await storage.read_pdf(document_id) == b"%PDF-3"
    assert not (tmp_path / "cache").exists()
