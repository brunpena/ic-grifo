"""Conversion stays outside the upload request and sources survive process restarts."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1 import documents
from app.services import document_upload, storage
from app.services.converters import ConversionError, SourceFile, UnsupportedFormatError


@pytest.mark.parametrize(
    "source,kind",
    [
        (SourceFile(b"%PDF-signature-only", "file.pdf"), "pdf"),
        (SourceFile(b"hello", "file.txt"), "text"),
        (SourceFile(b"<html></html>", "file.html"), "html"),
    ],
)
def test_source_validation_does_not_extract_content(monkeypatch, source, kind):
    convert = Mock(side_effect=AssertionError("request must not convert"))
    monkeypatch.setattr(document_upload.registry, "convert", convert)
    assert document_upload.validate_source(source) == kind
    convert.assert_not_called()


def test_source_validation_rejects_unsupported_and_invalid_signatures():
    with pytest.raises(UnsupportedFormatError):
        document_upload.validate_source(SourceFile(b"PK", "file.docx"))
    with pytest.raises(ConversionError, match="PDF"):
        document_upload.validate_source(SourceFile(b"bad", "file.pdf"))
    with pytest.raises(ConversionError, match="vazio"):
        document_upload.validate_source(SourceFile(b"  ", "file.txt"))


async def test_source_roundtrip_preserves_bytes_metadata_and_explicit_title(monkeypatch):
    saved = {}

    async def save(name, data, content_type):
        saved[name] = data

    async def read(name):
        return saved[name]

    monkeypatch.setattr(storage, "save_file", save)
    monkeypatch.setattr(storage, "read_file", read)
    document_id = uuid.uuid4()
    source = SourceFile(b"\xe1\x00\xff\n", "input.txt", "text/plain", "cp1252")
    convert = Mock(return_value=SimpleNamespace(title="inferred"))
    monkeypatch.setattr(document_upload.registry, "convert", convert)
    await document_upload.save_source(document_id, source, title="Chosen title")
    assert saved[storage.source_name(document_id)] is source.data
    convert.assert_not_called()
    converted = await document_upload.convert_source(document_id)
    assert converted.title == "Chosen title"
    assert convert.call_args.args[0] == source
    assert storage.source_name(document_id) in storage.document_files(document_id)
    assert storage.source_metadata_name(document_id) in storage.document_files(document_id)


async def test_upload_persists_source_outside_transaction_without_conversion(monkeypatch):
    target = SimpleNamespace(id=uuid.uuid4(), title="Existing analysis")
    user = SimpleNamespace(id=uuid.uuid4())
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=1),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
    )

    async def refresh(doc):
        doc.created_at = datetime.now(UTC)

    db.refresh = refresh
    monkeypatch.setattr(documents, "_target_analysis", AsyncMock(return_value=target))
    saved = []

    async def save(document_id, source, **kwargs):
        assert db.commit.await_count == 1
        db.add.assert_not_called()
        saved.append(document_id)

    monkeypatch.setattr(document_upload, "save_source", save)
    convert = Mock(side_effect=AssertionError("conversion ran inside request"))
    monkeypatch.setattr(document_upload.registry, "convert", convert)
    start = Mock()
    monkeypatch.setattr(documents.ingest, "start_processing", start)
    result = await documents._create_document(
        db, user, target.id, SourceFile(b"%PDF-signature-only", "contract.pdf")
    )
    assert result.status == "processing"
    assert result.page_count is None
    assert saved == [result.id]
    assert db.add.call_args.args[0].storage_path is None
    start.assert_called_once_with(
        result.id, source=SourceFile(b"%PDF-signature-only", "contract.pdf"), title=None
    )
    convert.assert_not_called()


async def test_corrupt_source_reports_conversion_error(monkeypatch):
    monkeypatch.setattr(storage, "read_file", AsyncMock(return_value=b"bad header"))
    with pytest.raises(ConversionError, match="recuperar"):
        await document_upload.convert_source(uuid.uuid4())
