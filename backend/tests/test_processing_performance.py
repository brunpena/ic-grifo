"""Regression tests for concurrent loads, bounded caches and paged validation."""

import asyncio
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.schemas.validation import ValidationPlan
from app.services import compliance, datasets, query_engine, rule_validation

CSV = b"value,label\n1,one\n2,two\n3,three\n"


@pytest.fixture(autouse=True)
def isolated_caches(monkeypatch):
    monkeypatch.setattr(query_engine, "_cache", OrderedDict())
    monkeypatch.setattr(query_engine, "_loading", {})
    monkeypatch.setattr(query_engine, "_cache_lock", asyncio.Lock())
    monkeypatch.setattr(rule_validation, "_indices", OrderedDict())
    monkeypatch.setattr(rule_validation, "_index_tasks", {})


def schema():
    return [column.to_dict() for column in datasets.parse_csv(CSV).columns]


def test_known_schema_skips_inference_and_rejects_changed_header(monkeypatch):
    columns = schema()

    def unexpected(*args):
        raise AssertionError("Known columns must not be inferred again")

    monkeypatch.setattr(datasets, "infer_column", unexpected)
    parsed = datasets.parse_csv(CSV, known_columns=columns)
    assert parsed.rows == [["1", "one"], ["2", "two"], ["3", "three"]]
    assert [c.to_dict() for c in parsed.columns] == columns
    with pytest.raises(datasets.DatasetError, match="cabeçalho"):
        datasets.parse_csv(CSV.replace(b"value,", b"changed,"), known_columns=columns)


async def test_different_dataset_reads_overlap_and_duplicates_share_load(monkeypatch):
    columns = schema()
    started = set()
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def read(name):
        started.add(name)
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return CSV

    monkeypatch.setattr(query_engine.storage, "read_file", read)
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    tasks = [
        asyncio.create_task(query_engine.load_dataset(i, len(CSV), columns))
        for i in (first_id, first_id, second_id)
    ]
    try:
        await asyncio.wait_for(both_started.wait(), 1)
    finally:
        release.set()
    first, duplicate, second = await asyncio.gather(*tasks)
    assert first is duplicate
    assert first is not second
    assert len(started) == 2
    assert first.typed_rows[0] == [1, "one"]


async def test_cached_dataset_does_not_wait_for_unrelated_slow_read(monkeypatch):
    columns = schema()
    cached_id = uuid.uuid4()
    cached = await query_engine.prime_dataset(cached_id, len(CSV), columns, datasets.parse_csv(CSV))
    started, release = asyncio.Event(), asyncio.Event()

    async def read(name):
        started.set()
        await release.wait()
        return CSV

    monkeypatch.setattr(query_engine.storage, "read_file", read)
    slow = asyncio.create_task(query_engine.load_dataset(uuid.uuid4(), len(CSV), columns))
    await started.wait()
    try:
        result = await asyncio.wait_for(query_engine.load_dataset(cached_id, len(CSV), columns), 1)
        assert result is cached
    finally:
        release.set()
        await slow


async def test_cancelled_waiter_does_not_cancel_shared_load(monkeypatch):
    columns = schema()
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def read(name):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return CSV

    monkeypatch.setattr(query_engine.storage, "read_file", read)
    dataset_id = uuid.uuid4()
    first = asyncio.create_task(query_engine.load_dataset(dataset_id, len(CSV), columns))
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    loaded = await query_engine.load_dataset(dataset_id, len(CSV), columns)
    assert loaded.raw_rows[0] == ["1", "one"]
    assert calls == 1


async def test_failed_load_can_be_retried(monkeypatch):
    columns = schema()
    calls = 0

    async def read(name):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise query_engine.storage.StorageError("synthetic")
        return CSV

    monkeypatch.setattr(query_engine.storage, "read_file", read)
    dataset_id = uuid.uuid4()
    with pytest.raises(query_engine.QueryError):
        await query_engine.load_dataset(dataset_id, len(CSV), columns)
    assert not query_engine._loading
    loaded = await query_engine.load_dataset(dataset_id, len(CSV), columns)
    assert loaded.typed_rows[0][0] == 1
    assert calls == 2


async def test_prime_reuses_rows_and_cache_obeys_byte_budget(monkeypatch):
    parsed = datasets.parse_csv(CSV)
    columns = [c.to_dict() for c in parsed.columns]
    first_id = uuid.uuid4()
    first = await query_engine.prime_dataset(first_id, len(CSV), columns, parsed)
    assert isinstance(first.raw_rows, query_engine.DuckDBRows)
    assert first.raw_rows[:] == parsed.rows
    assert await query_engine.load_dataset(first_id, len(CSV), columns) is first
    monkeypatch.setattr(query_engine, "CACHE_MAX_BYTES", first.memory_bytes + 1)
    second_id = uuid.uuid4()
    await query_engine.prime_dataset(second_id, len(CSV), columns, parsed)
    assert len(query_engine._cache) == 1
    assert next(iter(query_engine._cache))[0] == second_id
    monkeypatch.setattr(query_engine, "CACHE_MAX_BYTES", 1)
    await query_engine.prime_dataset(uuid.uuid4(), len(CSV), columns, parsed)
    assert len(query_engine._cache) == 1  # oversized value is returned, never retained


def validation_data():
    columns = [{"name": "value", "type": "integer", "semantic": {"confidence": "high"}}]
    dataset = SimpleNamespace(
        id=uuid.uuid4(),
        name="data",
        columns=columns,
        status="ready",
        size_bytes=100,
        original_size_bytes=None,
    )
    plan = ValidationPlan.model_validate(
        {
            "explanation": "Check value",
            "datasets": [
                {
                    "scope": {"dataset": "data", "conditions": []},
                    "checks": [
                        {
                            "left": {"kind": "column", "column": "value"},
                            "op": "gte",
                            "right": {"kind": "literal", "value": 50},
                            "explanation": "Minimum value",
                        }
                    ],
                }
            ],
        }
    )
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    compiled = compliance.compile_validation(
        plan.datasets[0],
        query_engine.DatasetRef(dataset.id, dataset.name, columns),
        checked_at.date(),
        [],
    )
    rows = [[i] for i in range(1000)]
    loaded = query_engine.LoadedDataset([[str(i)] for i in range(1000)], rows)
    return dataset, plan, checked_at, compiled, loaded


async def test_validation_pages_reuse_index_and_only_explain_returned_rows(monkeypatch):
    dataset, plan, checked_at, compiled, loaded = validation_data()
    evaluations = []
    original = compiled.evaluate

    def counted(row, explain=True):
        evaluations.append(explain)
        return original(row, explain=explain)

    monkeypatch.setattr(compiled, "evaluate", counted)
    index = await rule_validation._validation_index(plan, dataset, checked_at, compiled, loaded)
    assert evaluations == [False] * 1000
    evaluations.clear()
    same = await rule_validation._validation_index(plan, dataset, checked_at, compiled, loaded)
    assert same is index
    counts, total, page = compliance.evaluate_rows(
        compiled,
        loaded.raw_rows,
        loaded.typed_rows,
        offset=10,
        limit=20,
        verdict="conforme",
        index=same,
    )
    assert total == counts["passed_count"] == 950
    assert [r.index for r in page] == list(range(60, 80))
    assert evaluations == [True] * 20
    assert all(row.explanation for row in page)
    # Reference time, physical schema and semantic confidence form part of the key.
    refreshed = await rule_validation._validation_index(
        plan, dataset, checked_at + timedelta(days=1), compiled, loaded
    )
    assert refreshed is not same
    dataset.columns[0]["semantic"]["confidence"] = "low"
    uncertain = compliance.compile_validation(
        plan.datasets[0],
        query_engine.DatasetRef(dataset.id, dataset.name, dataset.columns),
        checked_at.date(),
        [],
    )
    changed = await rule_validation._validation_index(plan, dataset, checked_at, uncertain, loaded)
    assert changed is not same
    assert changed.counts["unknown_count"] == 1000


async def test_validation_index_single_flight_and_byte_limit(monkeypatch):
    dataset, plan, checked_at, compiled, loaded = validation_data()
    calls = 0
    original = compliance.index_rows

    def counted(compiled, rows):
        nonlocal calls
        calls += 1
        return original(compiled, rows)

    monkeypatch.setattr(compliance, "index_rows", counted)
    first, duplicate = await asyncio.gather(
        *[
            rule_validation._validation_index(plan, dataset, checked_at, compiled, loaded)
            for _ in range(2)
        ]
    )
    assert first is duplicate and calls == 1
    monkeypatch.setattr(rule_validation, "INDEX_CACHE_MAX_BYTES", first.memory_bytes + 1)
    later = await rule_validation._validation_index(
        plan, dataset, checked_at + timedelta(days=1), compiled, loaded
    )
    assert list(rule_validation._indices.values()) == [later]
    assert calls == 2


def test_counts_only_evaluation_does_not_format_evidence(monkeypatch):
    _, _, _, compiled, loaded = validation_data()

    def unexpected(value):
        raise AssertionError("Counts must not format evidence")

    monkeypatch.setattr(compliance, "_format", unexpected)
    counts, total, page = compliance.evaluate_rows(
        compiled, loaded.raw_rows, loaded.typed_rows, limit=0
    )
    assert counts["applicable_count"] == total == 1000
    assert counts["failed_count"] == 50
    assert page == []


async def test_column_interpretation_releases_transaction_and_overlaps_bases(monkeypatch):
    committed = False
    started = 0
    both_started = asyncio.Event()

    class Session:
        async def commit(self):
            nonlocal committed
            committed = True

    async def interpret(name, columns):
        nonlocal started
        assert committed
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), 1)
        return [{**c, "semantic": {"confidence": "high"}} for c in columns], None

    async def invalidate(db, analysis_id):
        pass

    monkeypatch.setattr(rule_validation, "interpret", interpret)
    monkeypatch.setattr(rule_validation, "invalidate_analysis", invalidate)
    monkeypatch.setattr(
        rule_validation, "get_settings", lambda: SimpleNamespace(llm_max_concurrency=2)
    )
    bases = [
        SimpleNamespace(name=str(i), columns=[{"name": "value"}], analysis_id=uuid.uuid4())
        for i in range(2)
    ]
    await rule_validation.ensure_meanings(Session(), bases, refresh=False)
    assert all(d.columns[0]["semantic"]["confidence"] == "high" for d in bases)
