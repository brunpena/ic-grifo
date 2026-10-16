from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(tags=["saúde"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool


@router.get("/health", summary="Verifica se a API e o banco respondem")
async def health(session: SessionDep) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return HealthResponse(status="ok" if db_ok else "degraded", database=db_ok)
