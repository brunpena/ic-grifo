"""Fluxos de ingestão com banco local e serviços externos simulados."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, update

from app.db.models import Document, Page, Word
from app.db.session import SessionLocal
from app.services import ingest, storage, validation_llm
from tests.test_documents import _login, _wait_ready, make_pdf


@pytest.mark.db
async def test_document_is_ready_to_highlight_while_columns_are_interpreted(
    migrated_db, client, monkeypatch
):
    await _login(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()
    interpreting, release = asyncio.Event(), asyncio.Event()

    async def meanings(name, columns):
        interpreting.set()
        await release.wait()
        return [{**c, "semantic": {"meaning": c["name"], "confidence": "high"}} for c in columns]

    async def unexpected_read(name):
        raise AssertionError(f"Upload bytes should be reused: {name}")

    monkeypatch.setattr(validation_llm, "interpret_columns", meanings)
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
        # A leitura do documento não espera a IA: ele fica pronto para grifar.
        assert (await _wait_ready(client, doc_id))["status"] == "ready"
    finally:
        release.set()
    assert (await client.get(f"/api/v1/documents/{doc_id}/rules")).json() == []


@pytest.mark.db
async def test_restart_resumes_source_and_reuses_pdf_without_duplicate_words(
    migrated_db, client, monkeypatch
):
    await _login(client)
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
async def test_resume_reads_the_saved_document_again(migrated_db, client):
    await _login(client)
    response = await client.post(
        "/api/v1/documents", files={"file": ("rules.pdf", make_pdf(1), "application/pdf")}
    )
    doc_id = response.json()["id"]
    assert (await _wait_ready(client, doc_id))["status"] == "ready"
    assert (await client.post(f"/api/v1/documents/{doc_id}/resume")).status_code == 409
    async with SessionLocal() as db:
        await db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(doc_id))
            .values(status="error", status_message="Falha simulada")
        )
        await db.commit()
    response = await client.post(f"/api/v1/documents/{doc_id}/resume")
    assert response.status_code == 202
    assert (await _wait_ready(client, doc_id))["status"] == "ready"
    async with SessionLocal() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(Page).where(Page.document_id == uuid.UUID(doc_id))
            )
            == 1
        )
