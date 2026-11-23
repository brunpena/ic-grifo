"""Tempo de cada requisição da API, gravado na tabela `request_logs`.

- `RequestMetricsMiddleware` mede a requisição do início ao último byte da resposta, e
  descobre a rota (o "tipo": `GET /api/v1/documents/{document_id}`).
- `instrument_engine` soma o tempo e a quantidade de comandos SQL de cada requisição,
  pelos eventos do SQLAlchemy.
- As linhas entram numa fila e uma tarefa em segundo plano grava em lotes: a resposta
  não espera o insert.

Só rotas em `/api/` são registradas, menos as da própria página de desempenho
(`/api/v1/performance`), que poluiriam as medições. Requisições com o cabeçalho
`X-Simulation-Id` (as das simulações) ficam marcadas como `source = "simulacao"`.
"""

import asyncio
import contextvars
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, event, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings

logger = logging.getLogger("app.request_metrics")

SIMULATION_HEADER = "x-simulation-id"
IGNORED_PREFIXES = ("/api/v1/performance",)
UNMATCHED_ROUTE = "(sem rota)"
# Rotas cujo primeiro segmento não é o nome do recurso.
_CATEGORY_ALIASES = {"me": "auth"}

_QUEUE_MAX = 10_000
_BATCH_MAX = 500
_PRUNE_EVERY_SECONDS = 3600


@dataclass
class RequestStats:
    """Contadores da requisição em andamento, preenchidos pelo SQLAlchemy e pelas deps."""

    db_ms: float = 0.0
    db_queries: int = 0
    user_id: uuid.UUID | None = None
    # Fecha ao terminar a resposta: tarefas em segundo plano que herdaram o contexto
    # (ex.: o processamento de um upload) não contam para a requisição.
    open: bool = True


_current: contextvars.ContextVar[RequestStats | None] = contextvars.ContextVar(
    "request_stats", default=None
)


def set_user(user_id: uuid.UUID) -> None:
    """Liga a requisição em andamento ao usuário logado (chamado na autenticação)."""
    stats = _current.get()
    if stats is not None:
        stats.user_id = user_id


# ----- tempo no banco -----

_instrumented: set = set()


def instrument_engine(engine: AsyncEngine) -> None:
    sync_engine = engine.sync_engine
    if sync_engine in _instrumented:
        return
    _instrumented.add(sync_engine)

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stats = _current.get()
        if stats is not None and stats.open and context is not None:
            context._metrics_started = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        started = getattr(context, "_metrics_started", None)
        stats = _current.get()
        if started is None or stats is None or not stats.open:
            return
        stats.db_ms += (time.perf_counter() - started) * 1000
        stats.db_queries += 1


# ----- rota e categoria -----


def _resolve_route(scope: Scope) -> tuple[str, str | None]:
    """Caminho completo da rota com os parâmetros (`/api/v1/documents/{document_id}`).

    O FastAPI deixa a rota em `scope["route"]`, mas com o caminho relativo ao router em
    que foi declarada (`/documents/{document_id}`); o prefixo vem do caminho real.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not template:
        return UNMATCHED_ROUTE, None
    tail = [p for p in template.split("/") if p]
    parts = [p for p in scope.get("path", "").split("/") if p]
    prefix = parts[: len(parts) - len(tail)] if len(parts) >= len(tail) else []
    return "/" + "/".join(prefix + tail), getattr(route, "name", None)


def category_of(route: str) -> str:
    parts = [p for p in route.split("/") if p]
    # /api/v1/<recurso>/...
    if len(parts) < 3 or parts[0] != "api":
        return "outros"
    return _CATEGORY_ALIASES.get(parts[2], parts[2])


def _simulation_id(scope: Scope) -> uuid.UUID | None:
    for name, value in scope.get("headers", []):
        if name.decode("latin-1").lower() == SIMULATION_HEADER:
            try:
                return uuid.UUID(value.decode("latin-1"))
            except ValueError:
                return None
    return None


class RequestMetricsMiddleware:
    """Middleware ASGI puro: não bufferiza a resposta, então streaming continua igual."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if (
            not path.startswith("/api/")
            or path.startswith(IGNORED_PREFIXES)
            or not get_settings().request_metrics_enabled
        ):
            await self.app(scope, receive, send)
            return

        stats = RequestStats()
        token = _current.set(stats)
        started = time.perf_counter()
        status_code = 500
        headers_at: float | None = None
        finished_at: float | None = None
        size = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, headers_at, finished_at, size
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            await send(message)
            if message["type"] == "http.response.start":
                headers_at = time.perf_counter()
            elif message["type"] == "http.response.body" and not message.get("more_body"):
                finished_at = time.perf_counter()
                stats.open = False

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            stats.open = False
            _current.reset(token)
            ended = finished_at or time.perf_counter()
            route, route_name = _resolve_route(scope)
            simulation_id = _simulation_id(scope)
            writer.submit(
                {
                    "created_at": datetime.now(UTC),
                    "method": scope.get("method", "GET"),
                    "route": route,
                    "route_name": route_name,
                    "category": category_of(route),
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": (ended - started) * 1000,
                    "headers_ms": (headers_at - started) * 1000 if headers_at else None,
                    "db_ms": stats.db_ms,
                    "db_queries": stats.db_queries,
                    "response_bytes": size,
                    "user_id": stats.user_id,
                    "source": "simulacao" if simulation_id else "app",
                    "simulation_id": simulation_id,
                }
            )


# ----- gravação em segundo plano -----


class _Writer:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_prune = 0.0
        self._warned_full = False

    def _ensure_started(self) -> asyncio.Queue[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        if self._queue is None or self._loop is not loop or self._task is None or self._task.done():
            self._loop = loop
            self._queue = asyncio.Queue(maxsize=_QUEUE_MAX)
            # Contexto vazio: os inserts da fila não podem contar como SQL de uma requisição.
            self._task = loop.create_task(self._run(), context=contextvars.Context())
        return self._queue

    def submit(self, row: dict[str, Any]) -> None:
        queue = self._ensure_started()
        try:
            queue.put_nowait(row)
        except asyncio.QueueFull:
            if not self._warned_full:
                self._warned_full = True
                logger.warning("request_metrics_queue_full")

    async def flush(self) -> None:
        """Espera a fila esvaziar (as linhas já enviadas estarem gravadas)."""
        if self._queue is not None and self._loop is asyncio.get_running_loop():
            await self._queue.join()

    async def stop(self) -> None:
        await self.flush()
        if self._task is not None:
            self._task.cancel()
        self._queue = self._task = self._loop = None

    async def _run(self) -> None:
        assert self._queue is not None
        queue = self._queue
        while True:
            batch = [await queue.get()]
            while len(batch) < _BATCH_MAX and not queue.empty():
                batch.append(queue.get_nowait())
            try:
                await self._insert(batch)
                await self._maybe_prune()
            except Exception:
                logger.warning("request_metrics_write_failed", exc_info=True)
            finally:
                for _ in batch:
                    queue.task_done()

    async def _insert(self, batch: list[dict[str, Any]]) -> None:
        from app.db.models import RequestLog
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            try:
                await db.execute(insert(RequestLog), batch)
                await db.commit()
            except IntegrityError:
                # Usuário excluído entre a requisição e a gravação: grava sem o vínculo.
                await db.rollback()
                await db.execute(insert(RequestLog), [{**r, "user_id": None} for r in batch])
                await db.commit()

    async def _maybe_prune(self) -> None:
        days = get_settings().request_log_retention_days
        now = time.monotonic()
        if not days or now - self._last_prune < _PRUNE_EVERY_SECONDS:
            return
        self._last_prune = now
        from app.db.models import RequestLog
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            await db.execute(delete(RequestLog).where(RequestLog.created_at < cutoff))
            await db.commit()


writer = _Writer()
