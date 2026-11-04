"""Cache durável e equivalência SQL/Python dos filtros e planos de conformidade."""

import asyncio
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest

from app.schemas.queries import StructuredQuery
from app.schemas.validation import DatasetCheck
from app.services import compliance, query_engine
from app.services.datasets import parse_csv
from app.services.duckdb_cache import CsvCacheError, CsvDuckDBCache
from app.services.query_engine import DatasetRef, compile_query, run
from tests.test_queries import CSV


@pytest.fixture
def local_cache(tmp_path):
    source = tmp_path / "contratos.csv"
    source.write_bytes(CSV)
    cache = CsvDuckDBCache(tmp_path / "contratos.duckdb")
    assert cache.sincronizar_csv(source)
    return cache, source


def test_cache_reopens_without_reading_csv_and_updates(local_cache, monkeypatch):
    cache, source = local_cache
    reopened = CsvDuckDBCache(cache.path)
    original = Path.read_bytes

    def no_read(path):
        raise AssertionError("CSV não deve ser lido no cache hit")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", no_read)
        assert not reopened.sincronizar_csv(source)
        assert reopened.buscar_por_id("002", "Número")["Valor"] == 80000
    source.write_bytes(original(source).replace(b"80.000,00", b"90.000,00"))
    assert reopened.sincronizar_csv(source)
    assert reopened.buscar_por_id("002", "Número")["Valor"] == 90000
    assert reopened.sincronizar_csv(source, forcar_atualizacao=True)


def test_bad_refresh_preserves_previous_table(local_cache):
    cache, source = local_cache
    source.write_text("a,b\n1,2,3\n", encoding="utf-8")
    with pytest.raises(CsvCacheError):
        cache.sincronizar_csv(source)
    assert cache.buscar_por_id("001", "Número")["Fornecedor"] == "Alfa Ltda"


def test_failed_import_rolls_back_and_removes_temporary_file(local_cache, monkeypatch):
    cache, source = local_cache
    # Um inteiro fora do HUGEINT falha no COPY, depois de começar a transação.
    source.write_text("id\n" + "9" * 60 + "\n", encoding="utf-8")
    with pytest.raises(CsvCacheError):
        cache.sincronizar_csv(source)
    assert cache.buscar_por_id("001", "Número") is not None
    assert sorted(p.name for p in source.parent.glob("*.csv")) == ["contratos.csv"]


def test_exact_id_and_partial_text_are_parameterized(local_cache):
    cache, _ = local_cache
    assert cache.buscar_por_id("001", "Número")["Número"] == "001"
    assert cache.buscar_por_id("x' OR 1=1 --", "Número") is None
    assert [r["Número"] for r in cache.buscar_texto("Fornecedor", "ALFA")] == ["001", "004"]
    assert cache.buscar_texto("Fornecedor", "%") == []
    assert cache.buscar_texto("Fornecedor", "_'") == []
    assert cache.buscar_texto("Fornecedor", "ALFA", ignorar_maiusculas=False) == []
    with pytest.raises(CsvCacheError, match="não existe"):
        cache.buscar_texto('x"; DROP TABLE dados; --', "a")
    with pytest.raises(CsvCacheError, match="limite"):
        cache.buscar_texto("Fornecedor", "a", limite=1001)


def test_read_connection_disallows_mutation_and_file_reads(local_cache):
    cache, source = local_cache
    with pytest.raises(CsvCacheError):
        cache.consultar("DELETE FROM dados")
    with pytest.raises(CsvCacheError):
        cache.consultar("SELECT * FROM read_csv(?)", [str(source)])


def test_threads_and_processes_can_share_cache(local_cache):
    cache, _ = local_cache

    def read(_):
        return CsvDuckDBCache(cache.path).buscar_por_id("001", "Número")["Número"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(read, range(12))) == ["001"] * 12
    script = (
        "import sys; from app.services.duckdb_cache import CsvDuckDBCache; "
        "assert CsvDuckDBCache(sys.argv[1]).buscar_por_id('001', 'Número')['Número'] == '001'"
    )
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(cache.path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    for child in children:
        _, error = child.communicate(timeout=30)
        assert child.returncode == 0, error.decode(errors="replace")


@pytest.mark.parametrize(
    "condition",
    [
        {"column": "Valor", "op": "gt", "value": 50000},
        {"column": "Assinatura", "op": "between", "value": ["2026-03-31", "2026-02-01"]},
        {"column": "Fornecedor", "op": "eq", "value": "ALFA LTDA"},
        {"column": "Fornecedor", "op": "contains", "value": "acao"},
        {"column": "Fornecedor", "op": "not_contains", "value": "alfa"},
        {"column": "Fornecedor", "op": "starts_with", "value": "ALFA"},
        {"column": "Fornecedor", "op": "ends_with", "value": "ltda"},
        {"column": "Fornecedor", "op": "in", "value": ["alfa ltda", "beta s.a."]},
        {"column": "Fornecedor", "op": "not_in", "value": ["alfa ltda"]},
        {"column": "Garantia", "op": "ne", "value": "10%"},
        {"column": "Garantia", "op": "is_null"},
        {"column": "Garantia", "op": "not_null"},
        {"column": "Ativo", "op": "eq", "value": False},
        {
            "logic": "or",
            "conditions": [
                {"column": "Valor", "op": "lt", "value": 5000},
                {"column": "Garantia", "op": "is_null"},
            ],
        },
    ],
)
def test_sql_filters_match_reference_engine(local_cache, condition, monkeypatch):
    cache, _ = local_cache
    metadata = cache.metadata()
    ref = DatasetRef(uuid.uuid4(), "contratos", metadata["columns"])
    loaded = query_engine._open_cached(cache, ref.columns, metadata["row_count"])
    compiled = compile_query(
        StructuredQuery.model_validate(
            {
                "dataset": ref.name,
                "conditions": [condition],
            }
        ),
        [ref],
    )
    expected = run(compiled, loaded.typed_rows[:])

    def no_scan(self):
        raise AssertionError("O filtro deve rodar no DuckDB, sem iterar linhas no Python")

    monkeypatch.setattr(query_engine.DuckDBRows, "__iter__", no_scan)
    # Se o caminho SQL tentar percorrer as linhas, o teste falha.
    assert run(compiled, loaded.typed_rows) == expected


def test_large_integer_ids_remain_exact(tmp_path):
    source = tmp_path / "ids.csv"
    first = 1234567890123456789012345
    source.write_text(f"id,label\n{first},one\n{first + 1},two\n", encoding="utf-8")
    cache = CsvDuckDBCache(tmp_path / "ids.duckdb")
    cache.sincronizar_csv(source)
    assert cache.buscar_por_id(first)["label"] == "one"
    columns = cache.metadata()["columns"]
    ref = DatasetRef(uuid.uuid4(), "ids", columns)
    loaded = query_engine._open_cached(cache, columns, 2)
    query = StructuredQuery.model_validate(
        {
            "dataset": "ids",
            "conditions": [{"column": "id", "op": "eq", "value": str(first + 1)}],
        }
    )
    assert run(compile_query(query, [ref]), loaded.typed_rows) == [1]


async def test_rule_query_keeps_total_and_fetches_only_pages(local_cache, monkeypatch):
    from types import SimpleNamespace

    from app.services import rule_queries

    cache, _ = local_cache
    columns = cache.metadata()["columns"]
    loaded = query_engine._open_cached(cache, columns, 4)
    dataset = SimpleNamespace(
        id=uuid.uuid4(), name="contratos", columns=columns, size_bytes=len(CSV)
    )

    async def load(*args):
        return loaded

    monkeypatch.setattr(rule_queries, "load_dataset", load)
    monkeypatch.setattr(query_engine, "MAX_STORED_MATCHES", 2)
    execution = await rule_queries.run_query(StructuredQuery(dataset=dataset.name), [dataset])
    assert isinstance(execution.rows, query_engine.SQLMatches)
    assert len(execution.rows) == 4
    assert execution.rows.first == [0, 1]
    assert execution.rows[2:3] == [2]
    assert execution.rows[-1] == 3
    assert execution.rows[4:5] == []


VALIDATION_CSV = (
    "id;Inicio;Fim;Valor;Garantia;GarantiaValor;Fornecedor\n"
    "001;31/01/2024;29/02/2024;60000;5%;3000;Ação Serviços\n"
    "002;01/01/2024;12/01/2024;80000;2%;1000;ALFA LTDA\n"
    "003;01/01/2024;;70000;;0;beta\n"
    "004;;12/01/2024;10000;5%;0;beta\n"
    "005;31/01/2024;01/01/2024;0;inválido;0; beta \n"
).encode()


def make_check(left, op, right=None):
    return {"left": left, "op": op, "right": right, "explanation": "Critério da regra"}


@pytest.mark.parametrize(
    "checks,logic",
    [
        (
            [
                make_check(
                    {"kind": "days_between", "column": "Inicio", "other_column": "Fim"},
                    "lte",
                    {"kind": "literal", "value": 10},
                )
            ],
            "and",
        ),
        (
            [
                make_check(
                    {"kind": "percentage", "column": "Garantia"},
                    "gte",
                    {"kind": "literal", "value": 5},
                )
            ],
            "and",
        ),
        (
            [
                make_check(
                    {"kind": "ratio_percent", "column": "GarantiaValor", "other_column": "Valor"},
                    "gte",
                    {"kind": "literal", "value": 5},
                )
            ],
            "and",
        ),
        (
            [
                make_check(
                    {"kind": "column", "column": "Fim"},
                    "lte",
                    {"kind": "deadline", "column": "Inicio", "value": 1, "unit": "months"},
                )
            ],
            "and",
        ),
        (
            [
                make_check(
                    {"kind": "column", "column": "Fornecedor"},
                    "contains",
                    {"kind": "literal", "value": "acao"},
                )
            ],
            "and",
        ),
        (
            [
                make_check(
                    {"kind": "column", "column": "Valor"},
                    "between",
                    {"kind": "literal", "value": [80000, 50000]},
                )
            ],
            "and",
        ),
        ([make_check({"kind": "column", "column": "Fim"}, "not_null")], "and"),
        (
            [
                make_check(
                    {"kind": "column", "column": "Valor"}, "gt", {"kind": "literal", "value": 70000}
                ),
                make_check({"kind": "column", "column": "Fim"}, "lt", {"kind": "today"}),
            ],
            "or",
        ),
    ],
)
@pytest.mark.parametrize("scope_mode", ["all", "filtered", "missing", "uncertain", "incomplete"])
def test_sql_validation_matches_reference_and_pages(tmp_path, checks, logic, scope_mode):
    parsed = parse_csv(VALIDATION_CSV)
    columns = [{**c.to_dict(), "semantic": {"confidence": "high"}} for c in parsed.columns]
    scope = []
    if scope_mode in ("filtered", "uncertain"):
        scope = [{"column": "Valor", "op": "gt", "value": 50000}]
    if scope_mode == "missing":
        scope = [{"column": "Inicio", "op": "gt", "value": "2023-01-01"}]
    if scope_mode == "uncertain":
        columns[3]["semantic"]["confidence"] = "low"
    ref = DatasetRef(uuid.uuid4(), "contratos", columns)
    plan = DatasetCheck.model_validate(
        {
            "scope": {"dataset": ref.name, "conditions": scope},
            "checks": checks,
            "logic": logic,
        }
    )
    compiled = compliance.compile_validation(
        plan,
        ref,
        date(2026, 1, 1),
        ["Evidência faltante"] if scope_mode == "incomplete" else [],
    )
    cache = CsvDuckDBCache(tmp_path / "validation.duckdb")
    cache.importar_processado(parsed, "test")
    loaded = query_engine._open_cached(cache, columns, len(parsed.rows))
    expected = compliance.evaluate_rows(compiled, loaded.raw_rows[:], loaded.typed_rows[:])
    actual = compliance.evaluate_rows(compiled, loaded.raw_rows, loaded.typed_rows)
    assert actual == expected
    index = compliance.index_rows(compiled, loaded.typed_rows)
    assert not any(isinstance(v, list) for v in index.indices.values())
    for verdict in (None, "conforme", "violacao", "inconclusiva"):
        page = compliance.evaluate_rows(
            compiled,
            loaded.raw_rows,
            loaded.typed_rows,
            offset=1,
            limit=1,
            verdict=verdict,
            index=index,
        )
        reference = compliance.evaluate_rows(
            compiled, loaded.raw_rows[:], loaded.typed_rows[:], offset=1, limit=1, verdict=verdict
        )
        assert page == reference


async def test_application_restart_uses_disk_cache(tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "duckdb_cache_dir", tmp_path)
    parsed = parse_csv(CSV)
    columns = [c.to_dict() for c in parsed.columns]
    dataset_id = uuid.uuid4()
    await query_engine.prime_dataset(dataset_id, len(CSV), columns, parsed)
    query_engine._cache.clear()

    async def no_download(*args):
        raise AssertionError("Cache persistente não pode baixar o CSV outra vez")

    def no_parse(*args, **kwargs):
        raise AssertionError("Cache persistente não pode refazer o parsing")

    monkeypatch.setattr(query_engine.storage, "read_file", no_download)
    monkeypatch.setattr(query_engine, "parse_csv", no_parse)
    loaded = await query_engine.load_dataset(dataset_id, len(CSV), columns)
    assert loaded.raw_rows[0][0] == "001"
    await query_engine.delete_dataset_cache(dataset_id)
    assert not list(tmp_path.glob("*.duckdb"))


async def test_concurrent_cold_loads_share_import(tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "duckdb_cache_dir", tmp_path)
    calls = 0

    async def read(*args):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return CSV

    monkeypatch.setattr(query_engine.storage, "read_file", read)
    columns = [c.to_dict() for c in parse_csv(CSV).columns]
    dataset_id = uuid.uuid4()
    loaded = await asyncio.gather(
        *[query_engine.load_dataset(dataset_id, len(CSV), columns) for _ in range(4)]
    )
    assert all(item is loaded[0] for item in loaded)
    assert calls == 1
