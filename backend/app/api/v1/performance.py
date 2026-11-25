"""Página de desempenho: tempo das requisições gravadas em `request_logs` e simulações.

Liberada para qualquer conta logada; as medições são do sistema inteiro (todas as contas).
As próprias rotas deste arquivo não são medidas (ver `app.core.request_metrics`).
"""

import asyncio
import math
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Query, Request
from sqlalchemy import ColumnElement, Select, func, literal_column, select

from app.api.deps import SessionDep, UserDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.request_metrics import IGNORED_PREFIXES, SIMULATION_HEADER, writer
from app.db.models import RequestLog
from app.schemas.common import error_responses
from app.schemas.performance import (
    CategoryStats,
    LatencyStats,
    MetricsSource,
    PerformanceSummaryOut,
    RequestLogOut,
    RouteStats,
    ServerStats,
    SimulationIn,
    SimulationOperationOut,
    SimulationOut,
    SimulationRunOut,
    TimelineOut,
    TimelinePoint,
)

router = APIRouter(prefix="/performance", tags=["desempenho"])

SinceHours = Annotated[float, Query(gt=0, le=24 * 90, description="Janela, em horas.")]
Source = Annotated[MetricsSource, Query(description="Uso real, simulações ou ambos.")]

# Operações que a simulação sabe montar. Só leituras: repetir centenas de vezes não
# altera dados nem gasta cota da IA.
OPERATIONS: list[SimulationOperationOut] = [
    SimulationOperationOut(key="health", method="GET", path="/api/v1/health", param=None),
    SimulationOperationOut(key="auth_me", method="GET", path="/api/v1/auth/me", param=None),
    SimulationOperationOut(key="analyses_list", method="GET", path="/api/v1/analyses", param=None),
    SimulationOperationOut(
        key="analysis_detail", method="GET", path="/api/v1/analyses/{analysis_id}", param="analysis"
    ),
    SimulationOperationOut(
        key="documents_list", method="GET", path="/api/v1/documents", param=None
    ),
    SimulationOperationOut(
        key="document_detail",
        method="GET",
        path="/api/v1/documents/{document_id}",
        param="document",
    ),
    SimulationOperationOut(
        key="document_file",
        method="GET",
        path="/api/v1/documents/{document_id}/file",
        param="document",
    ),
    SimulationOperationOut(
        key="document_rules",
        method="GET",
        path="/api/v1/documents/{document_id}/rules",
        param="document",
    ),
    SimulationOperationOut(
        key="document_messages",
        method="GET",
        path="/api/v1/documents/{document_id}/messages",
        param="document",
    ),
    SimulationOperationOut(
        key="rule_records", method="GET", path="/api/v1/rules/{rule_id}/records", param="rule"
    ),
]
_OPERATIONS_BY_KEY = {op.key: op for op in OPERATIONS}


# ----- consultas -----


def _p(q: float, column: ColumnElement) -> ColumnElement:
    return func.percentile_cont(q).within_group(column)


def _latency_columns() -> list[ColumnElement]:
    d = RequestLog.duration_ms
    return [
        func.count().label("count"),
        func.avg(d).label("avg_ms"),
        _p(0.5, d).label("p50_ms"),
        _p(0.95, d).label("p95_ms"),
        _p(0.99, d).label("p99_ms"),
        func.max(d).label("max_ms"),
    ]


def _server_errors() -> ColumnElement:
    return func.count().filter(RequestLog.status_code >= 500).label("server_errors")


def _filtered(stmt: Select, since: datetime, source: MetricsSource) -> Select:
    stmt = stmt.where(RequestLog.created_at >= since)
    if source != "all":
        stmt = stmt.where(RequestLog.source == source)
    return stmt


def _since(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def _latency(row) -> dict:  # noqa: ANN001
    return {
        "count": row.count,
        "avg_ms": row.avg_ms,
        "p50_ms": row.p50_ms,
        "p95_ms": row.p95_ms,
        "p99_ms": row.p99_ms,
        "max_ms": row.max_ms,
    }


def _route_summaries(request: Request) -> dict[tuple[str, str], str | None]:
    """Resumo de cada rota, lido do OpenAPI (já com os caminhos completos)."""
    out: dict[tuple[str, str], str | None] = {}
    for path, operations in request.app.openapi().get("paths", {}).items():
        for method, operation in operations.items():
            out[(method.upper(), path)] = operation.get("summary")
    return out


@router.get("/summary", summary="Tempo por tipo de requisição (método + rota) e por categoria")
async def summary(
    request: Request,
    _: UserDep,
    db: SessionDep,
    since_hours: SinceHours = 24,
    source: Source = "app",
) -> PerformanceSummaryOut:
    since = _since(since_hours)
    totals = (
        await db.execute(
            _filtered(
                select(
                    *_latency_columns(), _server_errors(), func.avg(RequestLog.db_ms).label("db")
                ),
                since,
                source,
            )
        )
    ).one()

    categories = (
        await db.execute(
            _filtered(
                select(
                    RequestLog.category,
                    *_latency_columns(),
                    _server_errors(),
                    func.sum(RequestLog.duration_ms).label("total_ms"),
                ),
                since,
                source,
            ).group_by(RequestLog.category)
        )
    ).all()

    routes = (
        await db.execute(
            _filtered(
                select(
                    RequestLog.method,
                    RequestLog.route,
                    func.max(RequestLog.route_name).label("route_name"),
                    func.max(RequestLog.category).label("category"),
                    *_latency_columns(),
                    _server_errors(),
                    func.count()
                    .filter(RequestLog.status_code.between(400, 499))
                    .label("client_errors"),
                    func.avg(RequestLog.db_ms).label("avg_db_ms"),
                    func.avg(RequestLog.db_queries).label("avg_db_queries"),
                    func.avg(RequestLog.response_bytes).label("avg_response_bytes"),
                    func.sum(RequestLog.duration_ms).label("total_ms"),
                    func.max(RequestLog.created_at).label("last_at"),
                ),
                since,
                source,
            )
            .group_by(RequestLog.method, RequestLog.route)
            .order_by(func.sum(RequestLog.duration_ms).desc())
        )
    ).all()

    summaries = _route_summaries(request)
    return PerformanceSummaryOut(
        since=since,
        totals=LatencyStats(**_latency(totals)),
        server_errors=totals.server_errors,
        avg_db_ms=totals.db,
        categories=sorted(
            (
                CategoryStats(
                    category=c.category,
                    server_errors=c.server_errors,
                    total_ms=c.total_ms or 0,
                    **_latency(c),
                )
                for c in categories
            ),
            key=lambda c: c.total_ms,
            reverse=True,
        ),
        routes=[
            RouteStats(
                method=r.method,
                route=r.route,
                route_name=r.route_name,
                summary=summaries.get((r.method, r.route)),
                category=r.category,
                server_errors=r.server_errors,
                client_errors=r.client_errors,
                avg_db_ms=r.avg_db_ms,
                avg_db_queries=r.avg_db_queries,
                avg_response_bytes=r.avg_response_bytes,
                total_ms=r.total_ms or 0,
                last_at=r.last_at,
                **_latency(r),
            )
            for r in routes
        ],
    )


@router.get("/requests", summary="Requisições individuais, das mais lentas ou das mais recentes")
async def list_requests(
    _: UserDep,
    db: SessionDep,
    since_hours: SinceHours = 24,
    source: Source = "app",
    method: str | None = None,
    route: str | None = None,
    category: str | None = None,
    simulation_id: uuid.UUID | None = None,
    order: Literal["slowest", "recent"] = "slowest",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[RequestLogOut]:
    stmt = _filtered(select(RequestLog), _since(since_hours), source)
    if method:
        stmt = stmt.where(RequestLog.method == method.upper())
    if route:
        stmt = stmt.where(RequestLog.route == route)
    if category:
        stmt = stmt.where(RequestLog.category == category)
    if simulation_id:
        stmt = stmt.where(RequestLog.simulation_id == simulation_id)
    stmt = stmt.order_by(
        RequestLog.duration_ms.desc() if order == "slowest" else RequestLog.created_at.desc()
    ).limit(limit)
    rows = (await db.scalars(stmt)).all()
    return [RequestLogOut.model_validate(r, from_attributes=True) for r in rows]


def _bucket_minutes(hours: float) -> int:
    if hours <= 1:
        return 1
    if hours <= 6:
        return 5
    if hours <= 24:
        return 15
    if hours <= 24 * 7:
        return 120
    return 24 * 60


@router.get("/timeline", summary="Evolução do tempo das requisições ao longo da janela")
async def timeline(
    _: UserDep,
    db: SessionDep,
    since_hours: SinceHours = 24,
    source: Source = "app",
    method: str | None = None,
    route: str | None = None,
) -> TimelineOut:
    minutes = _bucket_minutes(since_hours)
    # `minutes` vem da tabela acima, nunca do usuário.
    bucket = func.date_bin(
        literal_column(f"INTERVAL '{minutes} minutes'"),
        RequestLog.created_at,
        literal_column("TIMESTAMPTZ '2000-01-01 00:00:00+00'"),
    ).label("at")
    stmt = _filtered(
        select(
            bucket,
            func.count().label("count"),
            func.avg(RequestLog.duration_ms).label("avg_ms"),
            _p(0.95, RequestLog.duration_ms).label("p95_ms"),
            _server_errors(),
        ),
        _since(since_hours),
        source,
    )
    if method:
        stmt = stmt.where(RequestLog.method == method.upper())
    if route:
        stmt = stmt.where(RequestLog.route == route)
    rows = (await db.execute(stmt.group_by(bucket).order_by(bucket))).all()
    return TimelineOut(
        bucket_minutes=minutes,
        points=[
            TimelinePoint(
                at=r.at,
                count=r.count,
                avg_ms=r.avg_ms,
                p95_ms=r.p95_ms,
                server_errors=r.server_errors,
            )
            for r in rows
        ],
    )


# ----- simulações -----


@router.get("/operations", summary="Operações que a simulação sabe executar")
async def operations(_: UserDep) -> list[SimulationOperationOut]:
    return OPERATIONS


def _percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _client_stats(durations: list[float]) -> LatencyStats:
    values = sorted(durations)
    return LatencyStats(
        count=len(values),
        avg_ms=sum(values) / len(values) if values else None,
        p50_ms=_percentile(values, 0.5),
        p95_ms=_percentile(values, 0.95),
        p99_ms=_percentile(values, 0.99),
        max_ms=values[-1] if values else None,
    )


def _simulation_target(body: SimulationIn) -> tuple[str, str]:
    if body.operation == "custom":
        path = (body.path or "").strip()
        if (
            not path.startswith("/api/v1/")
            or path.startswith(IGNORED_PREFIXES)
            or ".." in path
            or "://" in path
        ):
            raise AppError(
                "Informe um caminho GET dentro de /api/v1 (fora de /api/v1/performance).",
                code="invalid_simulation_path",
                status_code=422,
            )
        return "GET", path
    op = _OPERATIONS_BY_KEY.get(body.operation)
    if op is None:
        raise AppError(
            "Operação de simulação desconhecida.", code="unknown_operation", status_code=422
        )
    values: dict[str, str] = {}
    if op.param is not None:
        field = f"{op.param}_id"
        value = getattr(body.params, field)
        if value is None:
            raise AppError(
                f"A operação precisa de `params.{field}`.", code="missing_param", status_code=422
            )
        values[field] = str(value)
    return op.method, op.path.format(**values)


@router.post(
    "/simulations",
    summary="Executa uma operação várias vezes, com concorrência, e mede cada chamada",
    description=(
        "As chamadas passam por toda a aplicação (middlewares, autenticação com a sua sessão, "
        "banco), dentro do próprio processo: não incluem a rede entre o navegador e a API. "
        "Ficam gravadas em `request_logs` com `source = simulacao`."
    ),
    responses=error_responses(401, 422),
)
async def run_simulation(
    body: SimulationIn, request: Request, user: UserDep, db: SessionDep
) -> SimulationOut:
    method, path = _simulation_target(body)
    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name, "")
    # Devolve a conexão ao pool: a simulação não pode ocupar uma das conexões que mede.
    await db.close()

    simulation_id = uuid.uuid4()
    semaphore = asyncio.Semaphore(body.concurrency)
    durations: list[float] = []
    status_counts: dict[str, int] = {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=request.app),
        base_url="http://simulacao",
        cookies={settings.session_cookie_name: cookie},
        headers={SIMULATION_HEADER: str(simulation_id)},
        timeout=120,
    ) as client:

        async def call() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.request(method, path)
                    key = str(response.status_code)
                except Exception as exc:  # erro sem resposta HTTP (ex.: exceção na rota)
                    key = type(exc).__name__
                durations.append((time.perf_counter() - started) * 1000)
                status_counts[key] = status_counts.get(key, 0) + 1

        wall_started = time.perf_counter()
        await asyncio.gather(*(call() for _ in range(body.iterations)))
        wall_ms = (time.perf_counter() - wall_started) * 1000

    server: ServerStats | None = None
    if settings.request_metrics_enabled:
        await writer.flush()
        row = (
            await db.execute(
                select(
                    *_latency_columns(),
                    func.avg(RequestLog.db_ms).label("db_ms"),
                    func.avg(RequestLog.db_queries).label("db_queries"),
                ).where(RequestLog.simulation_id == simulation_id)
            )
        ).one()
        if row.count:
            server = ServerStats(
                **_latency(row), avg_db_ms=row.db_ms, avg_db_queries=row.db_queries
            )

    return SimulationOut(
        simulation_id=simulation_id,
        operation=body.operation,
        method=method,
        path=path,
        iterations=body.iterations,
        concurrency=body.concurrency,
        wall_ms=wall_ms,
        throughput_rps=body.iterations / (wall_ms / 1000) if wall_ms else 0,
        client=_client_stats(durations),
        server=server,
        status_counts=status_counts,
        durations_ms=durations,
    )


@router.get("/simulations", summary="Simulações já executadas, da mais recente à mais antiga")
async def list_simulations(
    _: UserDep,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SimulationRunOut]:
    started = func.min(RequestLog.created_at)
    rows = (
        await db.execute(
            select(
                RequestLog.simulation_id,
                started.label("started_at"),
                func.max(RequestLog.method).label("method"),
                func.max(RequestLog.route).label("route"),
                func.count().label("count"),
                func.avg(RequestLog.duration_ms).label("avg_ms"),
                _p(0.95, RequestLog.duration_ms).label("p95_ms"),
                func.avg(RequestLog.db_ms).label("avg_db_ms"),
                func.count().filter(RequestLog.status_code >= 500).label("server_errors"),
            )
            .where(RequestLog.simulation_id.is_not(None))
            .group_by(RequestLog.simulation_id)
            .order_by(started.desc())
            .limit(limit)
        )
    ).all()
    return [SimulationRunOut.model_validate(r, from_attributes=True) for r in rows]
