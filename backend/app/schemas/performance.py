"""Contratos da página de desempenho (tempo das requisições e simulações)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MetricsSource = Literal["app", "simulacao", "all"]


class LatencyStats(BaseModel):
    count: int
    avg_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: float | None


class RouteStats(LatencyStats):
    """Um tipo de requisição: método + rota."""

    method: str
    route: str
    route_name: str | None
    summary: str | None = Field(description="Resumo da rota no OpenAPI, quando houver.")
    category: str
    server_errors: int = Field(description="Respostas 5xx.")
    client_errors: int = Field(description="Respostas 4xx.")
    avg_db_ms: float | None
    avg_db_queries: float | None
    avg_response_bytes: float | None
    total_ms: float = Field(description="Soma das durações: onde o sistema passa mais tempo.")
    last_at: datetime


class CategoryStats(LatencyStats):
    category: str
    server_errors: int
    total_ms: float


class PerformanceSummaryOut(BaseModel):
    since: datetime
    totals: LatencyStats
    server_errors: int
    avg_db_ms: float | None
    categories: list[CategoryStats]
    routes: list[RouteStats]


class RequestLogOut(BaseModel):
    id: int
    created_at: datetime
    method: str
    route: str
    category: str
    path: str
    status_code: int
    duration_ms: float
    headers_ms: float | None
    db_ms: float
    db_queries: int
    response_bytes: int
    source: str
    simulation_id: uuid.UUID | None


class TimelinePoint(BaseModel):
    at: datetime
    count: int
    avg_ms: float
    p95_ms: float
    server_errors: int


class TimelineOut(BaseModel):
    bucket_minutes: int
    points: list[TimelinePoint]


SimulationParam = Literal["analysis", "document", "rule"]


class SimulationOperationOut(BaseModel):
    key: str
    method: str
    path: str
    param: SimulationParam | None


class SimulationParams(BaseModel):
    analysis_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None


class SimulationIn(BaseModel):
    operation: str = Field(description="Chave de `/performance/operations` ou `custom`.")
    params: SimulationParams = Field(default_factory=SimulationParams)
    path: str | None = Field(
        default=None,
        description="Só para `custom`: caminho GET dentro de /api/v1 (pode ter query string).",
    )
    iterations: int = Field(default=20, ge=1, le=500)
    concurrency: int = Field(default=1, ge=1, le=20)


class ServerStats(LatencyStats):
    avg_db_ms: float | None
    avg_db_queries: float | None


class SimulationOut(BaseModel):
    simulation_id: uuid.UUID
    operation: str
    method: str
    path: str
    iterations: int
    concurrency: int
    wall_ms: float = Field(description="Tempo total da simulação.")
    throughput_rps: float = Field(description="Requisições concluídas por segundo.")
    client: LatencyStats = Field(description="Tempos vistos por quem chamou (inclui a fila).")
    server: ServerStats | None = Field(
        description="Tempos gravados pelo servidor em request_logs (nulo com a medição desligada)."
    )
    status_counts: dict[str, int]
    durations_ms: list[float] = Field(description="Duração de cada chamada, na ordem de término.")


class SimulationRunOut(BaseModel):
    """Uma simulação já executada, montada a partir de `request_logs`."""

    simulation_id: uuid.UUID
    started_at: datetime
    method: str
    route: str
    count: int
    avg_ms: float
    p95_ms: float
    avg_db_ms: float
    server_errors: int
