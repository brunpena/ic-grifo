import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.session import engine
from app.main import app


def test_cors_origins_from_comma_separated_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, https://b.com ,")
    assert Settings().cors_origins == ["http://a.com", "https://b.com"]


def test_secrets_are_not_exposed_in_repr():
    settings = Settings(gemini_api_key="sk-ant-segredo")
    assert "sk-ant-segredo" not in repr(settings)
    assert "sk-ant-segredo" not in str(settings.model_dump())


async def test_unknown_route_uses_error_format(client):
    resp = await client.get("/api/v1/nao-existe")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": "Recurso não encontrado."}}


async def test_app_error_uses_error_format(client):
    @app.get("/_test/app-error")
    async def _boom():
        raise NotFoundError("Documento não encontrado.")

    resp = await client.get("/_test/app-error")
    assert resp.status_code == 404
    assert resp.json()["error"] == {"code": "not_found", "message": "Documento não encontrado."}


async def test_cors_allows_configured_origin(client):
    resp = await client.options(
        "/api/v1/health",
        headers={"Origin": "https://front.exemplo.com", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") == "https://front.exemplo.com"
    resp = await client.options(
        "/api/v1/health",
        headers={"Origin": "https://outro.com", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in resp.headers


async def test_openapi_is_generated(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/health" in resp.json()["paths"]


@pytest.mark.db
async def test_health_with_database(migrated_db, client):
    resp = await client.get("/api/v1/health")
    assert resp.json() == {"status": "ok", "database": True}


@pytest.mark.db
async def test_migration_creates_schema(migrated_db):
    async with engine.connect() as conn:
        tables = set(
            (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            ).scalars()
        )
        indexes = set(
            (
                await conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
                )
            ).scalars()
        )
        hnsw = (
            await conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_rules_embedding_hnsw'")
            )
        ).scalar_one()
    assert {"documents", "pages", "words", "rules", "conversations", "messages"} <= tables
    assert {
        "ix_words_document_page",
        "ix_words_document_char_start",
        "ix_rules_document_char_start",
        "ix_rules_embedding_hnsw",
    } <= indexes
    assert "hnsw" in hnsw and "vector_cosine_ops" in hnsw
