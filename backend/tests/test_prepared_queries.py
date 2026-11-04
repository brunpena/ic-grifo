"""Interpretação semântica -> SQL preparada -> seleção executa somente a página."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.deps import require_user
from app.api.v1 import documents
from app.core.config import get_settings
from app.db.models import RuleQuery
from app.db.session import get_session
from app.main import app
from app.services import ingest, llm, query_engine, rule_queries
from app.services.datasets import parse_csv

CSV = (
    b"id;Fornecedor;Valor;Assinatura\n001;Alfa;60000;01/01/2026\n"
    b"002;Beta;20000;02/01/2026\n003;Alfa;80000;03/01/2026\n"
)


def source():
    parsed = parse_csv(CSV)
    columns = [
        {**c.to_dict(), "semantic": {"meaning": c.name, "confidence": "high"}}
        for c in parsed.columns
    ]
    dataset = SimpleNamespace(
        id=uuid.uuid4(),
        name="contratos",
        columns=columns,
        size_bytes=len(CSV),
        row_count=len(parsed.rows),
        analysis_id=uuid.uuid4(),
    )
    return parsed, dataset


def prepared(dataset):
    query = RuleQuery(id=uuid.uuid4(), rule_id=uuid.uuid4(), origin="ia", matched_rows=[])
    rule_queries.set_query(
        query,
        {
            "dataset": dataset.name,
            "conditions": [
                {"column": "Valor", "op": "gt", "value": 50000},
            ],
        },
        "ia",
    )
    rule_queries.prepare_query(query, [dataset])
    return query


async def test_generation_uses_meanings_and_saves_sql_without_running_records(monkeypatch):
    _, dataset = source()
    rules = [
        SimpleNamespace(
            id=uuid.uuid4(),
            type="obrigacao",
            summary="Garantia",
            excerpt="Contratos acima de 50 mil exigem garantia",
            dataset_ids=[],
        )
    ]

    class Session:
        get = AsyncMock(return_value=SimpleNamespace(analysis_id=dataset.analysis_id))
        commit = AsyncMock()

        def __init__(self):
            self.scalars = AsyncMock(side_effect=[SimpleNamespace(all=lambda: rules), []])
            self.added = []

        def add(self, value):
            self.added.append(value)

    db = Session()
    monkeypatch.setattr(rule_queries, "analysis_datasets", AsyncMock(return_value=[dataset]))

    async def generate(items, bases):
        assert all(c.get("semantic") for c in bases[0].columns)
        return {
            items[0].ref: llm.GeneratedQuery(
                dataset.name,
                {
                    "dataset": dataset.name,
                    "conditions": [{"column": "Valor", "op": "gt", "value": 50000}],
                },
                "Contratos acima de 50 mil",
            )
        }

    def no_execution(*args, **kwargs):
        raise AssertionError("Preparar consultas não pode abrir o cache ou executar registros")

    monkeypatch.setattr(llm, "generate_queries", generate)
    monkeypatch.setattr(rule_queries, "run_query", no_execution)
    monkeypatch.setattr(rule_queries, "load_dataset", no_execution)
    result = await rule_queries.generate_for_document(
        db, uuid.uuid4(), overwrite=False, only_related=False
    )
    assert result.generated == 1
    query = db.added[0]
    assert query.state == "pendente" and query.executed_at is None
    assert query.match_count is None and query.matched_rows == []
    assert "SELECT _row_id" in query.sql and "50000" not in query.sql
    assert list(query.sql_parameters.values()) == [50000]


async def test_select_runs_in_cached_database_without_ai_and_keeps_sql_parameterized(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(get_settings(), "duckdb_cache_dir", tmp_path)
    parsed, dataset = source()
    await query_engine.prime_dataset(dataset.id, len(CSV), dataset.columns, parsed)
    query = prepared(dataset)

    def no_ai(*args, **kwargs):
        raise AssertionError("Selecionar uma regra não pode chamar a IA")

    monkeypatch.setattr(llm, "_generate", no_ai)
    monkeypatch.setattr(query_engine.storage, "read_file", no_ai)
    query.sql = "DELETE FROM dados"  # SQL persistida não é executada sem validação.
    result = await rule_queries.execute_page(query, [dataset], offset=1, limit=1)
    assert result.total == 2 and [r.values[0] for r in result.rows] == ["003"]
    assert query.state == "ok" and query.match_count == 2 and query.executed_at
    assert query.matched_rows == []
    assert query.sql.startswith("SELECT _row_id")
    again = await rule_queries.execute_page(query, [dataset], offset=0, limit=100)
    assert [r.values[0] for r in again.rows] == ["001", "003"]


async def test_records_endpoint_accepts_prepared_query_and_returns_current_execution(
    client,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(get_settings(), "duckdb_cache_dir", tmp_path)
    parsed, dataset = source()
    await query_engine.prime_dataset(dataset.id, len(CSV), dataset.columns, parsed)
    query = prepared(dataset)
    rule = SimpleNamespace(id=query.rule_id)
    monkeypatch.setattr(documents, "_owned_rule", AsyncMock(return_value=rule))
    monkeypatch.setattr(documents, "_rule_query", AsyncMock(return_value=query))
    monkeypatch.setattr(documents, "_rule_datasets", AsyncMock(return_value=[dataset]))
    db = SimpleNamespace(commit=AsyncMock())

    async def session():
        yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    try:
        response = await client.get(f"/api/v1/rules/{rule.id}/records?limit=1")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 2 and data["rows"][0]["values"][0] == "001"
        assert data["query"]["state"] == "ok" and data["query"]["sql"]
        # Mesmo que houvesse IDs antigos salvos, cada seleção executa o filtro atual.
        query.matched_rows, query.match_count = [1], 1
        query.query["conditions"][0]["value"] = 70000
        second = (await client.get(f"/api/v1/rules/{rule.id}/records")).json()
        assert second["total"] == 1 and second["rows"][0]["values"][0] == "003"
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)


async def test_normal_generation_does_not_trigger_a_second_ai_validation(monkeypatch):
    doc_id = uuid.uuid4()
    monkeypatch.setattr(ingest, "_set_status", AsyncMock())
    monkeypatch.setattr(ingest, "_wait_for_datasets", AsyncMock(return_value=True))
    legacy = AsyncMock()
    monkeypatch.setattr(ingest, "_run_validation", legacy)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(ingest, "SessionLocal", Session)
    generate = AsyncMock(return_value=rule_queries.GenerationResult(generated=2))
    monkeypatch.setattr(rule_queries, "generate_for_document", generate)
    await ingest._generate_queries(doc_id, overwrite=False, only_related=False)
    generate.assert_awaited_once()
    legacy.assert_not_awaited()
    assert ingest._set_status.call_args.args[1] == "ready"
