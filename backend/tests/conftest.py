"""Configuração dos testes.

As variáveis precisam ser definidas antes de importar `app`, porque a configuração e o
engine do banco são criados na importação. Testes marcados com `db` usam o banco de
TEST_DATABASE_URL (ver docker-compose.dev.yml) e são pulados se ele não estiver acessível.
"""

import asyncio
import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent.parent
_dotenv = dotenv_values(BACKEND_DIR / ".env") if (BACKEND_DIR / ".env").exists() else {}

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _dotenv.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:54329/icgrifo_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_PGBOUNCER"] = "false"
os.environ["APP_ENV"] = "test"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="icgrifo-test-storage-")
os.environ["ANTHROPIC_API_KEY"] = "test-key-nao-usada"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,https://front.exemplo.com"

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


def _db_available() -> bool:
    async def probe() -> bool:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    return asyncio.run(probe())


DB_AVAILABLE = _db_available()


def pytest_collection_modifyitems(config, items):
    if DB_AVAILABLE:
        return
    skip = pytest.mark.skip(reason=f"Banco de testes indisponível em {TEST_DATABASE_URL}")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


@pytest.fixture(scope="session")
def migrated_db():
    """Recria o esquema do zero no banco de testes, uma vez por sessão."""
    if not DB_AVAILABLE:
        pytest.skip("Banco de testes indisponível")
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
