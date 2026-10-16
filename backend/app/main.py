import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.db.session import engine
from app.services.ingest import recover_interrupted

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("startup", extra={"env": get_settings().app_env})
    try:
        await recover_interrupted()
    except Exception:
        # Sem banco na subida, a API ainda responde (o /health mostra o problema).
        logger.warning("recover_interrupted_failed", exc_info=True)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="IC Grifo API",
        version="0.1.0",
        description=(
            "Extração e validação de regras (obrigações, proibições, prazos e condições) "
            "em documentos, mantendo cada regra ligada ao trecho exato de origem. "
            "Todas as posições de caracteres (`char_start`, `char_end`) estão em unidades UTF-16, "
            "compatíveis com strings JavaScript."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # O login usa cookie; o front chama a API com `credentials: "include"`.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
