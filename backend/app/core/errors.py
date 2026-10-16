"""Erros da API no formato `{ "error": { "code", "message" } }`, com mensagens em português."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.json import OrjsonResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


_HTTP_MESSAGES = {
    400: ("bad_request", "Requisição inválida."),
    401: ("unauthorized", "Faça login para continuar."),
    404: ("not_found", "Recurso não encontrado."),
    405: ("method_not_allowed", "Método não permitido."),
    413: ("payload_too_large", "Conteúdo grande demais."),
    415: ("unsupported_media_type", "Tipo de conteúdo não suportado."),
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> OrjsonResponse:
        return OrjsonResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> OrjsonResponse:
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
            parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
        message = "Dados inválidos. " + "; ".join(parts)
        return OrjsonResponse(_body("validation_error", message), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> OrjsonResponse:
        code, message = _HTTP_MESSAGES.get(exc.status_code, ("http_error", "Erro na requisição."))
        return OrjsonResponse(_body(code, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> OrjsonResponse:
        logger.exception("unhandled_error", extra={"error_type": type(exc).__name__})
        return OrjsonResponse(_body("internal_error", "Erro interno do servidor."), status_code=500)
