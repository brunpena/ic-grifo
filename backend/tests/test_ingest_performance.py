"""Fluxos de ingestão com banco local e serviços externos simulados."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, update

from app.db.models import Document, Page, Word
from app.db.session import SessionLocal
from app.services import ingest, llm, storage, validation_llm
from tests.test_documents import _login, _wait_ready, make_pdf


@pytest.mark.db
async def test_rule_extraction_waits_for_column_meanings(migrated_db, client, monkeypatch):
    await _login(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()
    interpreting, release, extracted = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def meanings(name, columns):
        interpreting.set()
        await release.wait()
        return [{**c, "semantic": {"meaning": c["name"], "confidence": "high"}} for c in columns]

    async def rules(text, on_progress=None, datasets=None, **kwargs):
        assert len(datasets) == 1 and datasets[0].columns[0]["name"] == "value"
        assert datasets[0].columns[0]["semantic"]["confidence"] == "high"
        extracted.set()
        return []

    async def unexpected_read(name):
        raise AssertionError(f"Upload bytes should be reused: {name}")

    monkeypatch.setattr(validation_llm, "interpret_columns", meanings)
    monkeypatch.setattr(llm, "extract_rules", rules)
    monkeypatch.setattr(storage, "read_file", unexpected_read)
    response = await client.post(
        f"/api/v1/analyses/{analysis['id']}/datasets",
        files={"file": ("data.csv", b"value\n1\n2\n", "text/csv")},
    )
    assert response.status_code == 202
    try:
        await asyncio.wait_for(interpreting.wait(), 3)
        dataset = (await client.get(f"/api/v1/datasets/{response.json()['id']}")).json()
        assert dataset["status"] == "processing" and dataset["columns"]
        assert dataset["row_count"] == 2
        response = await client.post(
            "/api/v1/documents",
            data={"analysis_id": analysis["id"]},
            files={"file": ("rules.pdf", make_pdf(1), "application/pdf")},
        )
        assert response.status_code == 202
        doc_id = response.json()["id"]
        assert not extracted.is_set()
        current = (await client.get(f"/api/v1/documents/{doc_id}")).json()
        assert current["status"] in ("processing", "extracting_rules")
    finally:
        release.set()
    ready = await _wait_ready(client, doc_id)
    assert ready["status"] == "ready"
    assert extracted.is_set()


@pytest.mark.db
async def test_restart_resumes_source_and_reuses_pdf_without_duplicate_words(
    migrated_db, client, monkeypatch
):
    await _login(client)

    async def no_rules(*args, **kwargs):
        return []

    monkeypatch.setattr(llm, "extract_rules", no_rules)
    with monkeypatch.context() as patch:
        patch.setattr(ingest, "start_processing", lambda *args, **kwargs: None)
        response = await client.post(
            "/api/v1/documents", files={"file": ("rules.pdf", make_pdf(1), "application/pdf")}
        )
    assert response.status_code == 202
    doc_id = uuid.UUID(response.json()["id"])
    await ingest.recover_interrupted()
    assert (await _wait_ready(client, str(doc_id)))["status"] == "ready"
    async with SessionLocal() as db:
        original_count = await db.scalar(
            select(func.count()).select_from(Word).where(Word.document_id == doc_id)
        )
        await db.execute(
            update(Document).where(Document.id == doc_id).values(status="extracting_rules")
        )
        await db.commit()
    await ingest.recover_interrupted()
    assert (await _wait_ready(client, str(doc_id)))["status"] == "ready"
    async with SessionLocal() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(Word).where(Word.document_id == doc_id)
            )
            == original_count
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(Page).where(Page.document_id == doc_id)
            )
            == 1
        )
    response = await client.delete(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 204
    for name in storage.document_files(doc_id):
        with pytest.raises(storage.StorageError):
            await storage.read_file(name)


@pytest.mark.db
async def test_resume_persists_packages_and_only_sends_missing(migrated_db, client, monkeypatch):
    from pydantic import SecretStr

    from app.core.config import get_settings
    from app.db.models import Rule

    await _login(client)
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("fake"))
    monkeypatch.setattr(get_settings(), "llm_chunk_chars", 60)
    monkeypatch.setattr(get_settings(), "llm_chunk_overlap", 0)
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", 1)
    calls = []
    fail = True

    async def extract(text, sentences, ids, datasets):
        calls.append(ids.start)
        if fail and ids.start > 0:
            raise llm.LlmApiError("Gemini overloaded")
        return [llm.ExtractedRule(
            "prazo", sentences[ids.start].start, sentences[ids.start].end, "Pacote",
        )]

    async def no_validation(*args, **kwargs):
        pass

    monkeypatch.setattr(llm, "extract_rules_from_chunk", extract)
    monkeypatch.setattr(ingest, "_run_validation", no_validation)
    response = await client.post(
        "/api/v1/documents", files={"file": ("rules.pdf", make_pdf(1), "application/pdf")}
    )
    assert response.status_code == 202
    doc_id = response.json()["id"]
    assert (await _wait_ready(client, doc_id))["status"] == "error"
    async with SessionLocal() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert len(doc.extraction_checkpoint["completed"]) == 1
    fail = False
    calls.clear()
    response = await client.post(f"/api/v1/documents/{doc_id}/resume")
    assert response.status_code == 202
    assert (await _wait_ready(client, doc_id))["status"] == "ready"
    assert calls and 0 not in calls
    async with SessionLocal() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        count = await db.scalar(select(func.count()).select_from(Rule).where(
            Rule.document_id == uuid.UUID(doc_id),
        ))
        assert count == len(doc.extraction_checkpoint["completed"])
    assert (await client.post(f"/api/v1/documents/{doc_id}/resume")).status_code == 409
