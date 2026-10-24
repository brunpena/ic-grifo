"""Processamento de um documento enviado: texto, palavras e regras.

Roda como tarefa assíncrona dentro do processo da API (um único worker, ver
docker-entrypoint.sh). O status do documento mostra a etapa atual para o front.
"""

import asyncio
import logging
import uuid

from sqlalchemy import insert, update

from app.core.logging import log_step
from app.db.models import Document, Page, Rule, Word
from app.db.session import SessionLocal
from app.services import llm
from app.services.pdf_text import ExtractedDocument, PdfReadError, extract_pdf
from app.services.storage import StorageError, read_pdf

logger = logging.getLogger(__name__)

# Referências às tarefas em andamento (sem isso o asyncio pode descartá-las).
_tasks: set[asyncio.Task] = set()


def start_processing(document_id: uuid.UUID, extracted: ExtractedDocument | None = None) -> None:
    task = asyncio.create_task(process_document(document_id, extracted))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _set_status(document_id: uuid.UUID, status: str, message: str | None = None) -> None:
    async with SessionLocal() as db:
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=status, status_message=message)
        )
        await db.commit()


async def process_document(
    document_id: uuid.UUID, extracted: ExtractedDocument | None = None
) -> None:
    """Grava as palavras e extrai as regras. `extracted` vem do conversor, que já leu o
    texto no upload; sem ele, o PDF guardado é lido de novo."""
    try:
        if extracted is None:
            with log_step(logger, "read_pdf", document_id=str(document_id)) as info:
                data = await read_pdf(document_id)
                extracted = await asyncio.to_thread(extract_pdf, data)
                info["pages"] = len(extracted.pages)
                info["chars"] = len(extracted.full_text)

        async with SessionLocal() as db:
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    full_text=extracted.full_text,
                    page_count=len(extracted.pages),
                    status="extracting_rules",
                    status_message=None,
                )
            )
            db.add_all(
                Page(document_id=document_id, page_number=p.number, width=p.width, height=p.height)
                for p in extracted.pages
            )
            await db.flush()
            if extracted.words:
                await db.execute(
                    insert(Word),
                    [
                        {
                            "document_id": document_id,
                            "page": w.page,
                            "text": w.text,
                            "char_start": w.char_start,
                            "char_end": w.char_end,
                            "x0": w.x0,
                            "y0": w.y0,
                            "x1": w.x1,
                            "y1": w.y1,
                        }
                        for w in extracted.words
                    ],
                )
            await db.commit()

        async def progress(done: int, total: int) -> None:
            await _set_status(
                document_id, "extracting_rules", f"Analisando trecho {done} de {total}"
            )

        with log_step(logger, "extract_rules", document_id=str(document_id)) as info:
            found = await llm.extract_rules(extracted.full_text, on_progress=progress)
            rules = dedupe_rules(found)
            info["found"] = len(found)
            info["kept"] = len(rules)

        async with SessionLocal() as db:
            db.add_all(
                Rule(
                    document_id=document_id,
                    type=r.type,
                    summary=r.summary[:200],
                    excerpt=extracted.full_text[r.start : r.end],
                    char_start=r.start,
                    char_end=r.end,
                    origin="ia",
                )
                for r in rules
            )
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="ready", status_message=None)
            )
            await db.commit()
    except (PdfReadError, StorageError) as exc:
        await _set_status(document_id, "error", str(exc))
    except llm.LlmUnavailableError as exc:
        await _set_status(document_id, "error", str(exc))
    except llm.LlmApiError as exc:
        logger.warning("process_document_llm_failed", extra={"document_id": str(document_id)})
        await _set_status(document_id, "error", str(exc))
    except Exception:
        logger.exception("process_document_failed", extra={"document_id": str(document_id)})
        await _set_status(
            document_id, "error", "Não foi possível analisar o documento. Tente enviar de novo."
        )


def dedupe_rules(found: list[llm.ExtractedRule]) -> list[llm.ExtractedRule]:
    """Descarta repetições (os blocos se sobrepõem) e ordena pela posição no texto."""
    kept: list[llm.ExtractedRule] = []
    for rule in sorted(found, key=lambda r: (r.start, r.end)):
        duplicate = any(
            other.type == rule.type
            and min(rule.end, other.end) - max(rule.start, other.start)
            > 0.5 * min(rule.end - rule.start, other.end - other.start)
            for other in kept
        )
        if not duplicate:
            kept.append(rule)
    return kept


async def recover_interrupted() -> None:
    """Na subida da API, documentos que estavam sendo processados viram erro."""
    async with SessionLocal() as db:
        await db.execute(
            update(Document)
            .where(Document.status.in_(("processing", "extracting_rules")))
            .values(
                status="error",
                status_message="O processamento foi interrompido. Envie o documento de novo.",
            )
        )
        await db.commit()
