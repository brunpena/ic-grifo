#!/bin/sh
set -e
# Aplica as migrations antes de subir a API (idempotente).
alembic upgrade head
# Um único worker: o pipeline de ingestão roda em tarefas assíncronas dentro do processo.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
