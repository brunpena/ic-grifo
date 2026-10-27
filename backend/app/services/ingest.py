"""Processamento de um documento enviado (texto, palavras e regras) e leitura das bases.

Roda como tarefa assíncrona dentro do processo da API (um único worker, ver
docker-entrypoint.sh). O status do documento mostra a etapa atual para o front.
"""

import asyncio
import logging
import uuid

from sqlalchemy import exists, insert, select, update

from app.core.logging import log_step
from app.db.models import Dataset, Document, Page, Rule, Word
from app.db.session import SessionLocal
from app.services import llm, rule_queries, rule_validation, storage
from app.services.datasets import DatasetError, parse_csv
from app.services.pdf_text import ExtractedDocument, PdfReadError, extract_pdf
from app.services.storage import StorageError, read_pdf

logger = logging.getLogger(__name__)

# Referências às tarefas em andamento (sem isso o asyncio pode descartá-las).
_tasks: set[asyncio.Task] = set()
_validation_requested: set[uuid.UUID] = set()


QUERIES_MESSAGE = "Gerando as buscas nas bases de dados"
QUERIES_INTERRUPTED = (
    "As regras foram encontradas, mas a geração das buscas foi interrompida. "
    "Use “Gerar buscas” para tentar de novo."
)


def _start(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def start_processing(document_id: uuid.UUID, extracted: ExtractedDocument | None = None) -> None:
    _start(process_document(document_id, extracted))


def start_dataset_processing(dataset_id: uuid.UUID) -> None:
    _start(process_dataset(dataset_id))


async def process_dataset(dataset_id: uuid.UUID) -> None:
    """Lê a base guardada no storage e grava o schema. As linhas não são guardadas: as
    buscas das regras leem o arquivo quando precisam (ver query_engine.load_dataset)."""
    values: dict = {"status": "error"}
    try:
        with log_step(logger, "process_dataset", dataset_id=str(dataset_id)) as info:
            data = await storage.read_file(storage.dataset_name(dataset_id))
            parsed = await asyncio.to_thread(parse_csv, data)
            async with SessionLocal() as db:
                dataset = await db.get(Dataset, dataset_id)
                if dataset is None:
                    return
                name = dataset.name
                analysis_id = dataset.analysis_id
                dataset.status_message = "Interpretando o significado das colunas com IA"
                await db.commit()
            columns, warning = await rule_validation.interpret(
                name, [c.to_dict() for c in parsed.columns]
            )
            values = {
                "status": "ready",
                "status_message": warning,
                "encoding": parsed.encoding,
                "delimiter": parsed.delimiter,
                "row_count": len(parsed.rows),
                "columns": columns,
            }
            info.update(rows=len(parsed.rows), columns=len(parsed.columns))
    except DatasetError as exc:
        values["status_message"] = str(exc)
    except StorageError:
        values["status_message"] = "O arquivo da base não foi encontrado. Envie a base de novo."
    except Exception:
        logger.exception("process_dataset_failed", extra={"dataset_id": str(dataset_id)})
        values["status_message"] = "Não foi possível ler a base. Envie de novo."
    async with SessionLocal() as db:
        await db.execute(update(Dataset).where(Dataset.id == dataset_id).values(**values))
        await db.commit()
    if values["status"] == "ready":
        async with SessionLocal() as db:
            await rule_validation.invalidate_analysis(db, analysis_id)
            await db.commit()
            ready_ids = list(
                await db.scalars(
                    select(Document.id).where(
                        Document.analysis_id == analysis_id,
                        Document.status.in_(("ready", "processing", "extracting_rules")),
                    )
                )
            )
        for document_id in ready_ids:
            start_validation(document_id)


def start_validation(
    document_id: uuid.UUID, *, refresh_columns: bool = False, reserved: bool = False
) -> None:
    _validation_requested.add(document_id)
    _start(_validate(document_id, refresh_columns=refresh_columns, reserved=reserved))


async def _validate(document_id: uuid.UUID, *, refresh_columns: bool, reserved: bool) -> None:
    # A reserva é atômica: uploads concorrentes de bases não iniciam duas avaliações.
    if not reserved:
        async with SessionLocal() as db:
            reservation = await db.scalar(
                update(Document)
                .where(Document.id == document_id, Document.status == "ready")
                .values(
                    status="extracting_rules", status_message="Validando todas as regras nas bases"
                )
                .returning(Document.id)
            )
            await db.commit()
        if reservation is None:
            async with SessionLocal() as db:
                current = await db.scalar(select(Document.status).where(Document.id == document_id))
            if current is None or current == "error":
                _validation_requested.discard(document_id)
            return
    _validation_requested.discard(document_id)
    await _run_validation(document_id, refresh_columns=refresh_columns)
    await _set_status(document_id, "ready")


async def _run_validation(document_id: uuid.UUID, *, refresh_columns: bool = False) -> None:
    _validation_requested.discard(document_id)
    await _set_status(document_id, "extracting_rules", "Validando todas as regras nas bases")
    try:
        async with SessionLocal() as db:
            await rule_validation.validate_document(
                db, document_id, refresh_columns=refresh_columns
            )
    except Exception:
        logger.exception("document_validation_failed", extra={"document_id": str(document_id)})
        async with SessionLocal() as db:
            await db.execute(
                update(Rule)
                .where(Rule.document_id == document_id)
                .values(
                    validation=rule_validation.result(
                        "erro", "A verificação foi interrompida. Valide novamente."
                    )
                )
            )
            await db.commit()


def start_query_generation(document_id: uuid.UUID, *, overwrite: bool) -> None:
    """Gera de novo as buscas (pedido da pessoa), com o documento em `extracting_rules`."""
    _start(_generate_queries(document_id, overwrite=overwrite, only_related=False))


async def _generate_queries(document_id: uuid.UUID, *, overwrite: bool, only_related: bool) -> None:
    """Etapa das buscas. Uma falha aqui não perde as regras: o documento fica pronto, com
    o motivo em `status_message`."""
    await _set_status(document_id, "extracting_rules", QUERIES_MESSAGE)
    message: str | None = None
    try:
        with log_step(logger, "generate_queries", document_id=str(document_id)) as info:
            async with SessionLocal() as db:
                result = await rule_queries.generate_for_document(
                    db, document_id, overwrite=overwrite, only_related=only_related
                )
            info.update(vars(result))
        if result.failed == 1:
            message = "1 busca gerada pela IA não passou na validação. Corrija na regra."
        elif result.failed:
            message = (
                f"{result.failed} buscas geradas pela IA não passaram na validação. "
                "Corrija nas regras."
            )
    except (llm.LlmUnavailableError, llm.LlmApiError) as exc:
        message = f"As regras foram encontradas, mas a IA não gerou as buscas: {exc}"
    except Exception:
        logger.exception("generate_queries_failed", extra={"document_id": str(document_id)})
        message = "As regras foram encontradas, mas não foi possível gerar as buscas."
    await _run_validation(document_id)
    await _set_status(document_id, "ready", message)


async def _set_status(document_id: uuid.UUID, status: str, message: str | None = None) -> None:
    async with SessionLocal() as db:
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=status, status_message=message)
        )
        await db.commit()
    if status == "ready" and document_id in _validation_requested:
        start_validation(document_id)
    elif status == "error":
        _validation_requested.discard(document_id)


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

        async with SessionLocal() as db:
            analysis_id = await db.scalar(
                select(Document.analysis_id).where(Document.id == document_id)
            )
            datasets = await rule_queries.analysis_datasets(db, analysis_id) if analysis_id else []
        dataset_ids = {d.name: d.id for d in datasets}

        with log_step(logger, "extract_rules", document_id=str(document_id)) as info:
            found = await llm.extract_rules(
                extracted.full_text,
                on_progress=progress,
                datasets=rule_queries.dataset_prompts(datasets),
            )
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
                    dataset_ids=[dataset_ids[n] for n in r.datasets if n in dataset_ids],
                )
                for r in rules
            )
            await db.commit()

        if datasets:
            await _generate_queries(document_id, overwrite=False, only_related=True)
        else:
            await _run_validation(document_id)
            await _set_status(document_id, "ready")
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
            continue
        # A mesma regra vista em dois blocos: junta as bases que cada um marcou.
        for other in kept:
            if other.type == rule.type and other.start <= rule.end and rule.start <= other.end:
                other.datasets = list(dict.fromkeys([*other.datasets, *rule.datasets]))
                break
    return kept


async def recover_interrupted() -> None:
    """Na subida da API, documentos que estavam sendo processados viram erro. Os que já
    tinham regras (paravam na geração das buscas) ficam prontos, com um aviso. Bases que
    estavam sendo lidas voltam a ser lidas: o arquivo já está no storage."""
    async with SessionLocal() as db:
        pending = (await db.scalars(select(Dataset.id).where(Dataset.status == "processing"))).all()
        for dataset_id in pending:
            start_dataset_processing(dataset_id)
        await db.execute(
            update(Rule)
            .where(
                Rule.document_id.in_(
                    select(Document.id).where(Document.status == "extracting_rules")
                )
            )
            .values(validation=None)
        )
        await db.execute(
            update(Document)
            .where(
                Document.status == "extracting_rules",
                exists().where(Rule.document_id == Document.id),
            )
            .values(status="ready", status_message=QUERIES_INTERRUPTED)
        )
        await db.execute(
            update(Document)
            .where(Document.status.in_(("processing", "extracting_rules")))
            .values(
                status="error",
                status_message="O processamento foi interrompido. Envie o documento de novo.",
            )
        )
        await db.commit()
