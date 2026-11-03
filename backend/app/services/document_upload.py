"""Durable document sources, accepted before conversion and text extraction."""

import asyncio
import json
import logging
import uuid

from app.services import storage
from app.services.converters import (
    ConversionError,
    ConvertedDocument,
    SourceFile,
    UnsupportedFormatError,
    registry,
)

logger = logging.getLogger(__name__)


def validate_source(source: SourceFile) -> str:
    """Only cheap checks run in the request; content extraction runs in the worker."""
    converter = registry.find(source)
    if converter is None:
        raise UnsupportedFormatError(registry.unsupported_message(source))
    if not source.data.strip():
        raise ConversionError("O arquivo está vazio.")
    if converter.source_type == "pdf" and not source.data.startswith(b"%PDF-"):
        raise ConversionError("O arquivo não é um PDF válido.")
    return converter.source_type


async def save_source(
    document_id: uuid.UUID, source: SourceFile, *, title: str | None = None
) -> None:
    # Metadados separados preservam o limite de tamanho do arquivo original e
    # evitam criar uma segunda cópia de todo o conteúdo na memória.
    metadata = json.dumps(
        {
            "filename": source.filename,
            "content_type": source.content_type,
            "charset": source.charset,
            "title": title,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    results = await asyncio.gather(
        storage.save_file(
            storage.source_name(document_id), source.data, "application/octet-stream"
        ),
        storage.save_file(storage.source_metadata_name(document_id), metadata, "application/json"),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            try:
                await storage.delete_files(storage.document_files(document_id))
            except Exception:
                logger.exception("source_cleanup_failed", extra={"document_id": str(document_id)})
            raise result


async def convert_source(
    document_id: uuid.UUID, source: SourceFile | None = None, *, title: str | None = None
) -> ConvertedDocument:
    """Load the durable source after restart, then convert outside the event loop."""
    if source is not None:
        converted = await asyncio.to_thread(registry.convert, source)
        if title:
            converted.title = title
        return converted
    metadata_bytes, data = await asyncio.gather(
        storage.read_file(storage.source_metadata_name(document_id)),
        storage.read_file(storage.source_name(document_id)),
    )
    try:
        metadata = json.loads(metadata_bytes)
        source = SourceFile(
            data=data,
            filename=metadata["filename"],
            content_type=metadata["content_type"],
            charset=metadata["charset"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ConversionError(
            "Não foi possível recuperar o arquivo original. Envie novamente."
        ) from exc
    converted = await asyncio.to_thread(registry.convert, source)
    if metadata.get("title"):
        converted.title = metadata["title"]
    return converted
