# IC Grifo — backend

API FastAPI para converter documentos, extrair regras, consultar bases CSV e verificar
se os registros cumprem os critérios. Usa PostgreSQL/SQLAlchemy, DuckDB embarcado,
PyMuPDF e Gemini.

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

As variáveis `GEMINI_API_KEY`, `GEMINI_API_KEY_2` e `GEMINI_API_KEY_3` aceitam até três
credenciais distintas. Defina cada variável uma única vez: uma definição vazia no
final do `.env` sobrescreve uma chave preenchida anteriormente. Reinicie a API após
alterar esse arquivo, pois a configuração fica em memória.
As [cotas do Gemini são por projeto](https://ai.google.dev/gemini-api/docs/rate-limits),
não por chave; várias chaves do mesmo projeto não multiplicam a cota disponível.
O serviço alterna as credenciais e aplica o prazo de pausa informado pelo Google
para cada combinação de credencial e modelo. HTTP 503 indica indisponibilidade,
enquanto HTTP 429 com uma métrica diária identifica o limite diário do projeto/modelo.

- API: http://localhost:8000/api/v1
- OpenAPI: http://localhost:8000/openapi.json
- Documentação interativa: http://localhost:8000/docs

## Consultas CSV com DuckDB embarcado

`CsvDuckDBCache`, em [duckdb_cache.py](app/services/duckdb_cache.py), importa o CSV uma
vez e persiste registros tipados em um arquivo `.duckdb`. Não exige servidor, Docker
ou serviço analítico. O PostgreSQL existente continua guardando usuários, documentos
e metadados da aplicação.

```python
from app.services.duckdb_cache import CsvDuckDBCache

cache = CsvDuckDBCache("./data/contratos.duckdb")
atualizou = cache.sincronizar_csv("./contratos.csv")
contrato = cache.buscar_por_id("001", coluna="id")
fornecedores = cache.buscar_texto("Fornecedor", "Alfa", limite=20)
# Reimportar mesmo se tamanho e mtime_ns não mudaram:
# cache.sincronizar_csv("./contratos.csv", forcar_atualizacao=True)
```

A sincronização compara caminho absoluto, tamanho e data de modificação em
nanossegundos. Uma falha na recarga preserva a tabela anterior por transação.
`buscar_por_id` retorna o primeiro registro ou `None`; `buscar_texto` retorna dicionários,
aceita paginação e usa `ILIKE` (ou `LIKE` com `ignorar_maiusculas=False`). Os parâmetros
são vinculados, inclusive textos com aspas, `%` ou `_`. A coluna chamada `id` recebe
um índice na importação; outros identificadores podem exigir varredura vetorizada.

No fluxo da aplicação, o parser do upload alimenta o cache diretamente, sem reler o
arquivo. Os caches ficam em `DUCKDB_CACHE_DIR` (padrão `./data/duckdb`), com nomes por
UUID da base e versão física. Após reiniciar, o sistema reutiliza esses arquivos;
bases antigas ou caches apagados são reconstruídos a partir do storage. Os uploads
são imutáveis por UUID: substituir uma base exige um novo envio. A API apaga o cache
ao excluir a base ou a análise. Preserve essa pasta em disco persistente no deploy.

Ao encerrar o uso pelo botão **Nova análise**, a interface chama
`POST /api/v1/analyses/{id}/close` e aguarda a remoção dos DuckDBs dessa análise.
O encerramento interrompe tarefas pendentes e libera referências em memória, sem
apagar os CSVs originais, documentos ou regras já salvos. Processamentos interrompidos
ficam sinalizados para retomada explícita, evitando recriar o cache após reiniciar a API.
Ao sair da tela ou fechar a aba, a interface também tenta enviar a chamada com
`keepalive`; a entrega depende de o navegador e a conexão ainda estarem disponíveis.

A IA identifica o significado das colunas e traduz cada regra em filtros e critérios
JSON. O compilador valida esses critérios e gera SQL parametrizado para o DuckDB.
As consultas e seus parâmetros ficam salvos em `rule_queries.sql` e
`rule_queries.sql_parameters`, sem executar pesquisas durante a geração.
Ao selecionar uma regra, `GET /api/v1/rules/{id}/records` executa sua consulta no
DuckDB em cache e devolve somente a página solicitada, com a contagem total.
Selecionar outra regra ou paginar não chama a IA. A tabela exibe a consulta da regra
selecionada por padrão; não há avaliação automática de todas as linhas/regras.
O modelo recebe metadados e exemplos por coluna, sem os registros completos, e não
calcula o resultado da consulta. Consultas corrigidas manualmente são preservadas.
O fluxo aguarda a interpretação das colunas antes de extrair e preparar as regras.
A rota de validação geral continua disponível para pedidos explícitos via API.

Aplique a migration `0009` antes de iniciar a API com esta versão:

```powershell
uv run alembic upgrade head
```

Cada operação usa sua própria conexão, fecha-a ao terminar e mantém um lock de arquivo
entre threads/processos. O acesso ao mesmo `.duckdb` é **serializado**, inclusive nas
leituras; bases diferentes podem ser consultadas simultaneamente. Isso permite vários
workers locais sem manter um escritor aberto em um processo enquanto outro lê.
Para paralelizar leituras do mesmo arquivo, todos os processos devem abrir apenas em
`read_only=True`, coordenando uma janela sem leitores para atualizar o cache, conforme
a [documentação de concorrência do DuckDB](https://duckdb.org/docs/stable/connect/concurrency.html).
Esta implementação escolhe o lock por arquivo para coordenar automaticamente as recargas.
Não promete latência instantânea: ela depende do filtro, volume, disco e fila do lock.

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
