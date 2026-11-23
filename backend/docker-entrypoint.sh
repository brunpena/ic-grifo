#!/bin/sh
set -e
# Aplica as migrations antes de subir a API (idempotente).
alembic upgrade head
# Um único worker: o pipeline de ingestão roda em tarefas assíncronas dentro do processo.
# Keep-alive acima dos 60 s usuais de balanceadores: o padrão do uvicorn (5 s) fecha a
# conexão entre as ações da pessoa e obriga um novo handshake TCP/TLS a cada clique.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' \n  --timeout-keep-alive "${UVICORN_KEEP_ALIVE:-75}"
