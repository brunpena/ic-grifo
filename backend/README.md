# IC Grifo — backend

API FastAPI para converter documentos, extrair regras, consultar bases CSV e verificar
se os registros cumprem os critérios. Usa PostgreSQL/SQLAlchemy, PyMuPDF e Gemini.

## Documentação para estudar o código

- [Roteiro de leitura](../docs/roteiro-de-leitura.md)
- [Arquitetura e modelo de dados](../docs/arquitetura.md)
- [Fluxogramas](../docs/fluxos.md)
- [Mapa de cada arquivo do backend](../docs/backend.md)
- [API e contratos](../docs/api.md)
- [Validação com exemplos](../docs/validacao.md)
- [Configuração e diagnóstico](../docs/desenvolvimento.md)

Os pontos de entrada são [app/main.py](app/main.py),
[app/api/v1/router.py](app/api/v1/router.py) e
[app/services/ingest.py](app/services/ingest.py).

## Executar localmente

Pré-requisitos: Python 3.12, uv e Docker para banco local.
Os comandos a seguir começam na pasta backend; só copie o ambiente se ainda não existir.

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
uv sync
docker compose -f docker-compose.dev.yml up -d --wait
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Configure DATABASE_URL e GEMINI_API_KEY no ambiente. As migrations modificam o banco
configurado; confirme o destino antes de executar.

- API: http://localhost:8000/api/v1
- OpenAPI: http://localhost:8000/openapi.json
- Documentação interativa: http://localhost:8000/docs

## Testes

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:54329/icgrifo_test"
uv run pytest
```

Os testes db recriam o esquema do banco de testes e são pulados quando ele não responde.
Não use um banco com dados reais. Os testes da IA usam simulações.

## Deploy

O Dockerfile e o entrypoint aplicam migrations e iniciam um processo da API.
O compose de produção ainda contém nomes antigos de variáveis da IA; confira o
[guia de operação](../docs/desenvolvimento.md) antes de utilizá-lo.

O [resumo operacional da validação](VALIDACAO.md) permanece disponível nesta pasta.
