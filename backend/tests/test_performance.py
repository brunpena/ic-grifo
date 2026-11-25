import uuid

import pytest

from app.api.v1.performance import _percentile, _simulation_target
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.request_metrics import _resolve_route, category_of, writer
from app.schemas.performance import SimulationIn


class _Route:
    def __init__(self, path: str, name: str = "rota") -> None:
        self.path = path
        self.name = name


def test_route_template_gets_router_prefix():
    scope = {"route": _Route("/documents/{document_id}/file"), "path": "/api/v1/documents/x/file"}
    assert _resolve_route(scope) == ("/api/v1/documents/{document_id}/file", "rota")


def test_unmatched_route():
    assert _resolve_route({"path": "/api/v1/nada"})[0] == "(sem rota)"


def test_category_groups_by_resource():
    assert category_of("/api/v1/documents/{document_id}/rules") == "documents"
    assert category_of("/api/v1/me") == "auth"
    assert category_of("(sem rota)") == "outros"


def test_percentile_interpolates():
    values = [10.0, 20.0, 30.0, 40.0]
    assert _percentile(values, 0.5) == 25
    assert _percentile(values, 1) == 40
    assert _percentile([], 0.5) is None


def test_simulation_target_fills_params():
    rule_id = uuid.uuid4()
    body = SimulationIn(operation="rule_records", params={"rule_id": rule_id})
    assert _simulation_target(body) == ("GET", f"/api/v1/rules/{rule_id}/records")


@pytest.mark.parametrize(
    "path", ["/api/v1/performance/summary", "/outra/coisa", "/api/v1/../x", "http://x/api/v1/a"]
)
def test_custom_simulation_rejects_unsafe_paths(path):
    with pytest.raises(AppError):
        _simulation_target(SimulationIn(operation="custom", path=path))


def test_simulation_requires_param():
    with pytest.raises(AppError):
        _simulation_target(SimulationIn(operation="document_rules"))


@pytest.fixture
def metrics_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "request_metrics_enabled", True)


async def _login(client) -> None:
    email = f"perf-{uuid.uuid4().hex[:8]}@exemplo.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"name": "Perf", "email": email, "password": "senha-forte-1"},
    )
    assert resp.status_code == 201


@pytest.mark.db
async def test_requests_are_recorded_by_route(migrated_db, metrics_on, client):
    await _login(client)
    for _ in range(3):
        assert (await client.get("/api/v1/documents")).status_code == 200
    await writer.flush()

    summary = (await client.get("/api/v1/performance/summary?since_hours=1")).json()
    route = next(
        r for r in summary["routes"] if r["route"] == "/api/v1/documents" and r["method"] == "GET"
    )
    assert route["count"] >= 3
    assert route["category"] == "documents"
    assert route["avg_db_queries"] >= 1
    assert route["summary"]
    # As rotas da própria página não entram nas medições.
    assert not any(r["route"].startswith("/api/v1/performance") for r in summary["routes"])

    slowest = (
        await client.get("/api/v1/performance/requests?since_hours=1&route=/api/v1/documents")
    ).json()
    assert slowest and all(r["route"] == "/api/v1/documents" for r in slowest)

    timeline = (await client.get("/api/v1/performance/timeline?since_hours=1")).json()
    assert timeline["bucket_minutes"] == 1
    assert sum(p["count"] for p in timeline["points"]) >= 3


@pytest.mark.db
async def test_simulation_is_measured_and_tagged(migrated_db, metrics_on, client):
    await _login(client)
    resp = await client.post(
        "/api/v1/performance/simulations",
        json={"operation": "analyses_list", "iterations": 6, "concurrency": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status_counts"] == {"200": 6}
    assert len(body["durations_ms"]) == 6
    assert body["server"]["count"] == 6

    runs = (await client.get("/api/v1/performance/simulations")).json()
    assert runs[0]["simulation_id"] == body["simulation_id"]
    assert runs[0]["route"] == "/api/v1/analyses"

    sim_only = (
        await client.get("/api/v1/performance/summary?since_hours=1&source=simulacao")
    ).json()
    assert sim_only["totals"]["count"] >= 6


async def test_performance_requires_login(client):
    assert (await client.get("/api/v1/performance/summary")).status_code == 401
