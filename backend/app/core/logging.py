"""Logs estruturados em JSON (uma linha por evento) e medição de tempo das etapas."""

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import orjson

# Atributos padrão do LogRecord que não devem ir para o JSON como campos extras.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

# Nomes de campos que nunca devem aparecer em log.
_SECRET_HINTS = ("key", "token", "secret", "password", "authorization")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            if any(h in k.lower() for h in _SECRET_HINTS):
                v = "***"
            payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return orjson.dumps(payload, default=str).decode()


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # O Uvicorn instala handlers próprios em texto; redireciona tudo para o formato JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    # Bibliotecas HTTP registram URLs e cabeçalhos em DEBUG; mantenha-as discretas.
    for noisy in ("httpx", "httpcore", "anthropic", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextmanager
def log_step(logger: logging.Logger, step: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Registra a duração de uma etapa. Campos adicionados ao dict retornado vão para o log."""
    extra: dict[str, Any] = dict(fields)
    start = time.perf_counter()
    try:
        yield extra
    except Exception:
        extra["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
        logger.exception("step_failed", extra={"step": step, **extra})
        raise
    extra["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
    logger.info("step_done", extra={"step": step, **extra})
