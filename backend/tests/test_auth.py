import uuid

import httpx
import pytest

from app.core.security import hash_password, hash_token, verify_password
from app.main import app


def test_password_hash_roundtrip():
    stored = hash_password("segredo-forte")
    assert stored.startswith("scrypt$")
    assert "segredo-forte" not in stored
    assert verify_password("segredo-forte", stored)
    assert not verify_password("outra-senha", stored)
    assert not verify_password("segredo-forte", "formato-invalido")


def test_same_password_gets_different_salts():
    assert hash_password("abc12345") != hash_password("abc12345")


def test_token_hash_is_stable_and_hides_token():
    assert hash_token("tok") == hash_token("tok")
    assert "tok" not in hash_token("tok")


def _email() -> str:
    return f"pessoa-{uuid.uuid4().hex[:8]}@Exemplo.com"


async def _register(client: httpx.AsyncClient, email: str, password: str = "senha-forte-1"):
    return await client.post(
        "/api/v1/auth/register", json={"name": " Ana ", "email": email, "password": password}
    )


@pytest.fixture
async def other_client():
    """Um segundo navegador, com seus próprios cookies."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_me_requires_login(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.db
async def test_register_login_logout_flow(migrated_db, client):
    email = _email()
    resp = await _register(client, email)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Ana"
    assert body["email"] == email.lower()
    assert "password_hash" not in body
    cookie = resp.headers["set-cookie"]
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower()

    assert (await client.get("/api/v1/auth/me")).json()["email"] == email.lower()

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    resp = await client.post(
        "/api/v1/auth/login", json={"email": email.upper(), "password": "senha-forte-1"}
    )
    assert resp.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


@pytest.mark.db
async def test_login_with_wrong_password_or_unknown_email(migrated_db, client):
    email = _email()
    await _register(client, email)
    client.cookies.clear()
    for payload in (
        {"email": email, "password": "senha-errada"},
        {"email": _email(), "password": "senha-forte-1"},
    ):
        resp = await client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code == 401
        assert resp.json()["error"] == {
            "code": "invalid_credentials",
            "message": "E-mail ou senha incorretos.",
        }


@pytest.mark.db
async def test_register_rejects_duplicate_email_and_short_password(migrated_db, client):
    email = _email()
    assert (await _register(client, email)).status_code == 201
    resp = await _register(client, email.upper())
    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "Já existe uma conta com este e-mail."
    assert (await _register(client, _email(), password="curta")).status_code == 422
    resp = await client.post(
        "/api/v1/auth/register", json={"name": "Ana", "email": "sem-arroba", "password": "x" * 8}
    )
    assert resp.status_code == 422


@pytest.mark.db
async def test_update_profile(migrated_db, client, other_client):
    taken = _email()
    await _register(other_client, taken)
    await _register(client, _email())

    resp = await client.patch(
        "/api/v1/me", json={"name": "Ana Souza", "job_title": " Analista ", "organization": "ACME"}
    )
    assert resp.status_code == 200
    expected = {"name": "Ana Souza", "job_title": "Analista", "organization": "ACME"}
    assert expected.items() <= resp.json().items()

    resp = await client.patch("/api/v1/me", json={"job_title": "  "})
    assert resp.json()["job_title"] is None
    assert resp.json()["organization"] == "ACME"

    resp = await client.patch("/api/v1/me", json={"email": taken})
    assert resp.status_code == 409


@pytest.mark.db
async def test_change_password_ends_other_sessions(migrated_db, client, other_client):
    email = _email()
    await _register(client, email)
    await other_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "senha-forte-1"}
    )
    assert (await other_client.get("/api/v1/auth/me")).status_code == 200

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "errada", "new_password": "nova-senha-123"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "wrong_password"

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "senha-forte-1", "new_password": "nova-senha-123"},
    )
    assert resp.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (await other_client.get("/api/v1/auth/me")).status_code == 401

    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "nova-senha-123"}
    )
    assert resp.status_code == 200
