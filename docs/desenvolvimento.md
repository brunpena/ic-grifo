# Desenvolvimento e operação

[Índice](README.md) · [Arquitetura](arquitetura.md) · [API](api.md)

## Pré-requisitos

- Python 3.12: o backend exige `>=3.12,<3.13`.
- uv para instalar e executar o ambiente Python.
- Node.js compatível com o Next e com `import.meta.dirname`, utilizado pelo script da
  raiz; Node 22+ atende a esse caminho. O pacote Next instalado declara `>=20.9.0`.
- npm para dependências e comandos da interface.
- Docker quando usar o PostgreSQL local do compose.
- Chave do Gemini para as operações reais de IA.

Os exemplos desta página usam PowerShell e começam na raiz do repositório.

## Primeira preparação

Os comandos abaixo só criam os arquivos de ambiente se eles ainda não existirem.

```powershell
npm ci
npm --prefix frontend ci

if (-not (Test-Path -LiteralPath frontend/.env.local)) {
    Copy-Item -LiteralPath frontend/.env.example -Destination frontend/.env.local
}

Push-Location backend
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
uv sync
Pop-Location
```

Edite `backend/.env` para definir a chave de IA e conferir o destino de
`DATABASE_URL`. Em `frontend/.env.local`, configure a URL base da API sem
`/api/v1` no final. Os arquivos reais de ambiente não devem fazer parte da documentação
nem dos commits.

## Subir os dois processos

```powershell
npm run dev
```

O [package.json](../package.json) usa concurrently. O script
[dev-backend.mjs](../scripts/dev-backend.mjs) procura a venv do backend, sobe Docker
apenas para banco local, aplica migrations e inicia watchfiles/Uvicorn. O frontend
usa o comando de desenvolvimento do Next.

Confirme o destino do banco antes: a inicialização aplica migrations no
`DATABASE_URL` configurado. `create_app` sozinho não aplica migrations.

## Executar separadamente

Em um terminal:

```powershell
Set-Location backend
docker compose -f docker-compose.dev.yml up -d --wait
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Em outro, a partir da raiz:

```powershell
npm --prefix frontend run dev
```

O compose publica PostgreSQL em 54329, com banco de desenvolvimento `icgrifo`.
O script SQL cria `icgrifo_test` na primeira inicialização do volume. Em volumes
antigos, não presuma que esse SQL será executado novamente.

## Migrations e contrato

```powershell
Push-Location backend
uv run alembic current
uv run alembic upgrade head
Pop-Location

npm --prefix frontend run gen:api
```

`gen:api` consulta o OpenAPI da API configurada. Também aceita uma URL base ou um
arquivo local, conforme [frontend/README.md](../frontend/README.md).

A sequência de uma alteração de contrato é: schemas/modelos → migration quando
necessária → rotas → OpenAPI → tipos gerados → hooks/componentes → testes e documentação.

## Testes

Use um banco dedicado: a fixture `migrated_db` faz downgrade até a base e recria o
esquema. Não aponte `TEST_DATABASE_URL` para um banco com dados reais.

```powershell
Push-Location backend
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:54329/icgrifo_test"
uv run pytest
Pop-Location
```

Os testes de IA usam simulações de transporte ou das funções do modelo. O conftest
limpa `GEMINI_API_KEY` para não usar a chave real por acidente. Testes marcados `db`
são pulados quando o banco de testes não responde.

Para focar em uma parte:

```powershell
Push-Location backend
uv run pytest tests/test_compliance.py -q
uv run pytest tests/test_validation_api.py -q
uv run ruff check app tests
Pop-Location

npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

A presença de testes pulados não verifica o fluxo com banco. O build da interface
verifica compilação e geração de páginas; não comprova uma chamada real ao Gemini.

## Configuração que influencia o fluxo

Os valores efetivos estão em
[config.py](../backend/app/core/config.py) e no ambiente da execução.

| Grupo | Variáveis principais | Efeito |
| --- | --- | --- |
| Aplicação | `APP_ENV`, `LOG_LEVEL` | Ambiente e nível de log. |
| Navegador/API | `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` | Origens aceitas e destino das chamadas. |
| Sessão | `SESSION_COOKIE_NAME`, `SESSION_DAYS` | Nome e duração do cookie/token. |
| Cookie | `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE` | Comportamento HTTP/HTTPS e envio entre sites. |
| Banco | `DATABASE_URL`, `DATABASE_PGBOUNCER`, `DATABASE_POOL_SIZE` | Conexão e pool SQLAlchemy/asyncpg. |
| Arquivos | `STORAGE_BACKEND`, `LOCAL_STORAGE_DIR` | Disco local ou Supabase. |
| Storage externo | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `SUPABASE_MAX_FILE_MB` | Bucket privado, credencial do servidor e limite configurado. |
| Documentos | `MAX_UPLOAD_MB`, `MAX_PASTED_CHARS`, `URL_FETCH_TIMEOUT_SECONDS` | Limites de entrada e download. |
| CSV | `MAX_DATASET_MB` | Limite de upload; vazio significa sem esse limite de aplicação. O Storage pode impor outro. |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_THINKING_LEVEL` | Provedor e geração de respostas. |
| Paralelismo | `LLM_MAX_CONCURRENCY`, `LLM_HEDGE_SECONDS` | Concorrência por operação/lote e reforço de requisição lenta. |
| Blocos de texto | `LLM_CHUNK_CHARS`, `LLM_CHUNK_OVERLAP` | Tamanho e sobreposição da extração. |

A chave do Storage fica no backend. Variáveis `NEXT_PUBLIC_*` fazem parte do
cliente público; não devem conter chaves privadas.

### Declaração não significa execução ativa

`MAX_DATASET_ROWS` e `MAX_DATASET_COLUMNS` existem em Settings, e o parser aceita
limites por argumento. Porém o leitor atual de ingestão chama `parse_csv(data)`
sem repassar essas duas opções. Não conte com elas como limites aplicados nesse caminho.

`LLM_RATE_LIMIT_PER_MINUTE` também está declarado, mas não há limitador por minuto
ligado a ele. Concorrência, retries e mensagens de quota são mecanismos separados.

As opções `EMBEDDING_*` estão preparadas na configuração, e a dimensão do vetor é
usada no modelo/migration. Não existe um pipeline ativo de busca semântica nessas telas.

## Diagnóstico por sintoma

| Sintoma | Onde investigar |
| --- | --- |
| API não inicia | Venv, DATABASE_URL, migrations e logs do script de desenvolvimento. |
| Health responde degraded | Conectividade/credenciais do banco. HTTP 200 sozinho não significa banco saudável. |
| Interface não conecta | URL da API, CORS, credenciais e mensagens de ApiError. |
| Login não persiste | Cookie, HTTPS, SameSite e envio com credentials include. |
| CSV falha após upload | status_message da base, parser e leitura do Storage em process_dataset. |
| CSV pronto, mas regra inconclusiva | Confiança e significado das colunas, missing_data e critérios do plano. |
| Documento sem texto | PDF digitalizado precisa de OCR antes do envio; HTML dependente de JavaScript pode exigir texto colado. |
| Regra não aparece grifada | Intervalos da extração, Word, rule_boxes e coordenadas normalizadas. |
| Resultados pedem nova validação | Fonte ou significado mudou; conferir assinaturas e estado das bases. |
| Chat falha depois de iniciar | Evento SSE error, logs de llm.stream_chat e quota/conexão do modelo. |

Os logs JSON incluem evento, nível, contexto e duração de etapas via `log_step`.
O script de benchmark chama a IA real para medir extração; ele não substitui os testes.

## Deploy existente

O [Dockerfile](../backend/Dockerfile) constrói a API e o
[entrypoint](../backend/docker-entrypoint.sh) aplica migrations antes de iniciar um
processo Uvicorn. Não há worker externo de tarefas.

O [compose de produção](../backend/docker-compose.yml) ainda mapeia
`ANTHROPIC_API_KEY` e `LLM_MODEL`. O código atual lê `GEMINI_API_KEY` e
`GEMINI_MODEL`, e o Dockerfile não copia o .env local. Portanto, usar esse compose
sem alinhar as variáveis não configura a IA atual.

O healthcheck da imagem verifica a resposta HTTP. Para avaliar o banco, leia também
o corpo de `/api/v1/health`.

## Arquivos da raiz e saídas das ferramentas

| Caminho | Papel |
| --- | --- |
| [.gitignore](../.gitignore) | Ignora dependências node_modules na raiz. |
| [package.json](../package.json) | Comandos para iniciar API e interface juntas ou separadas. |
| [package-lock.json](../package-lock.json) | Dependências travadas dos comandos da raiz, incluindo concurrently. |
| [scripts/dev-backend.mjs](../scripts/dev-backend.mjs) | Preparação do banco, migrations e reload da API. |
| [README.md](../README.md) | Entrada principal e navegação do projeto. |
| [docs/README.md](README.md) | Índice do material de estudo. |
| [.next/build/package.json](../.next/build/package.json) | Artefato gerado de build já versionado na raiz. |

Os arquivos JavaScript e source maps de `.next/build/chunks/` também estão
versionados, mas são saídas do bundler, não módulos de negócio para editar ou estudar.
Cada `.js` é código transformado e cada `.js.map` relaciona esse código às fontes.

Outras saídas locais, como `frontend/.next/`, `node_modules/`, `backend/.venv/`,
caches, bytecode e dados de Storage local, não são a documentação da implementação.
Os mapas de [backend](backend.md) e [frontend](frontend.md) cobrem os arquivos mantidos.
