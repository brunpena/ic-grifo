from fastapi import APIRouter

from app.api.v1 import auth, documents, health

# Rotas que exigem login declaram a dependência `UserDep`/`AuthDep` (ver app.api.deps).
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(documents.router)
