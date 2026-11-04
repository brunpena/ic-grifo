"""Encerramento de um uso: autorização, isolamento e remoção real do cache local."""

import asyncio
import uuid
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.deps import require_user
from app.core.config import get_settings
from app.db.models import Document
from app.db.session import get_session
from app.main import app
from app.services import datasets, ingest, query_engine, rule_validation
from tests.test_processing_performance import validation_data


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "duckdb_cache_dir", tmp_path)
    monkeypatch.setattr(query_engine, "_cache", OrderedDict())
    monkeypatch.setattr(query_engine, "_loading", {})
    monkeypatch.setattr(query_engine, "_cache_lock", asyncio.Lock())
    monkeypatch.setattr(rule_validation, "_indices", OrderedDict())
    monkeypatch.setattr(rule_validation, "_index_tasks", {})
    monkeypatch.setattr(rule_validation, "_index_datasets", {})
    monkeypatch.setattr(ingest, "_tasks", set())
    monkeypatch.setattr(ingest, "_tasks_by_owner", {})
    monkeypatch.setattr(ingest, "_validation_requested", set())
    monkeypatch.setattr(ingest, "_queries_requested", set())


async def test_close_removes_only_owned_analysis_cache_and_keeps_originals(
    client,
    tmp_path,
    isolated_state,
    monkeypatch,
):
    user_id, analysis_id, dataset_id, document_id = [uuid.uuid4() for _ in range(4)]
    other_dataset_id = uuid.uuid4()
    original = tmp_path / "original.csv"
    original.write_bytes(b"id,label\n001,one\n002,two\n")
    parsed = datasets.parse_csv(original.read_bytes())
    columns = [c.to_dict() for c in parsed.columns]
    for target in (dataset_id, other_dataset_id):
        await query_engine.prime_dataset(target, original.stat().st_size, columns, parsed)

    class Session:
        get = AsyncMock(return_value=SimpleNamespace(user_id=user_id))
        commit = AsyncMock()
        execute = AsyncMock()

        async def scalars(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            return [document_id] if entity is Document else [dataset_id]

    session = Session()

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=user_id)
    try:
        response = await client.post(f"/api/v1/analyses/{analysis_id}/close")
        assert response.status_code == 204
        assert not list(tmp_path.glob(f"{dataset_id}-*.duckdb"))
        assert list(tmp_path.glob(f"{other_dataset_id}-*.duckdb"))
        assert not any(key[0] == dataset_id for key in query_engine._cache)
        assert original.exists()
        assert len(session.execute.call_args_list) == 2
        assert all(
            str(call.args[0]).startswith("UPDATE") for call in session.execute.call_args_list
        )
        # Fechamento repetido não falha nem toca na outra análise.
        assert (await client.post(f"/api/v1/analyses/{analysis_id}/close")).status_code == 204
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)


async def test_close_rejects_another_users_analysis(client, isolated_state, monkeypatch):
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(user_id=uuid.uuid4())))
    stop = AsyncMock()
    monkeypatch.setattr(ingest, "stop_analysis_work", stop)

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    try:
        response = await client.post(f"/api/v1/analyses/{uuid.uuid4()}/close")
        assert response.status_code == 404
        stop.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)


async def test_stop_cancels_only_tasks_of_the_closed_analysis(isolated_state):
    document_id, dataset_id, other_id = [uuid.uuid4() for _ in range(3)]
    started = []
    finished = []

    async def work(owner):
        started.append(owner)
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(owner)

    owners = [("document", document_id), ("dataset", dataset_id), ("document", other_id)]
    for owner in owners:
        ingest._start(work(owner), owner=owner)
    await asyncio.sleep(0)
    ingest._validation_requested.update((document_id, other_id))
    ingest._queries_requested.update((document_id, other_id))
    await ingest.stop_analysis_work([document_id], [dataset_id])
    assert len(started) == 3
    assert set(finished) == set(owners[:2])
    assert ingest._validation_requested == {other_id}
    assert ingest._queries_requested == {other_id}
    assert set(ingest._tasks_by_owner) == {owners[2]}
    await ingest.stop_analysis_work([other_id], [])


async def test_close_releases_only_the_selected_validation_indices(isolated_state):
    first, plan, checked_at, compiled, loaded = validation_data()
    other, other_plan, other_time, other_compiled, other_loaded = validation_data()
    await rule_validation._validation_index(plan, first, checked_at, compiled, loaded)
    other_index = await rule_validation._validation_index(
        other_plan,
        other,
        other_time,
        other_compiled,
        other_loaded,
    )
    await rule_validation.clear_dataset_indices([first.id])
    assert list(rule_validation._indices.values()) == [other_index]
    assert set(rule_validation._index_datasets.values()) == {other.id}


async def test_cleanup_waits_for_an_import_that_outlives_its_caller(
    tmp_path,
    isolated_state,
    monkeypatch,
):
    dataset_id = uuid.uuid4()
    parsed = datasets.parse_csv(b"id\n001\n")
    columns = [c.to_dict() for c in parsed.columns]
    started, release = asyncio.Event(), asyncio.Event()
    persist = query_engine._persist

    async def delayed():
        started.set()
        await release.wait()
        return await asyncio.to_thread(
            persist, query_engine._key(dataset_id, 7, columns), parsed, columns
        )

    waiter = asyncio.create_task(
        query_engine._cached_load(
            query_engine._key(dataset_id, 7, columns),
            delayed,
        )
    )
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    cleanup = asyncio.create_task(query_engine.delete_dataset_cache(dataset_id))
    await asyncio.sleep(0)
    assert not cleanup.done()
    release.set()
    await cleanup
    assert not list(tmp_path.glob("*.duckdb"))
    assert not query_engine._cache
