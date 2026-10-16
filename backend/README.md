# IC Grifo — back-end

API (FastAPI) do sistema de validação de regras em documentos. A documentação completa
(arquitetura, variáveis e exemplos) será escrita na etapa final; por enquanto:

## Rodando localmente

Pré-requisitos: [uv](https://docs.astral.sh/uv/) e Docker.

```bash
cd backend
cp .env.example .env                              # ajuste as chaves
docker compose -f docker-compose.dev.yml up -d    # Postgres + pgvector na porta 54329
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

- API: http://localhost:8000/api/v1
- OpenAPI (contrato oficial): http://localhost:8000/openapi.json — docs em http://localhost:8000/docs

## Testes

```bash
uv run pytest
```

Os testes marcados com `db` usam o banco `icgrifo_test` do `docker-compose.dev.yml`
(criado automaticamente) e são pulados se ele não estiver acessível.

## Deploy (Coolify)

`docker-compose.yml` sobe apenas a API; banco e Storage ficam no Supabase. O entrypoint
aplica as migrations (`alembic upgrade head`) antes de iniciar o Uvicorn.
