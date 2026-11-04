"""Processamento de um documento enviado (texto, palavras e regras) e leitura das bases.

Roda como tarefa assíncrona dentro do processo da API (um único worker, ver
docker-entrypoint.sh). O status do documento mostra a etapa atual para o front.
"""

import asyncio
import logging
import uuid

from sqlalchemy import delete, exists, insert, select, update

from app.core.logging import log_step
from app.db.models import Analysis, Dataset, Document, Page, Rule, Word
from app.db.session import SessionLocal
from app.services import document_upload, llm, rule_queries, rule_validation, storage
from app.services.converters import ConversionError, SourceFile
from app.services.datasets import DatasetError, parse_csv
from app.services.pdf_text import ExtractedDocument, PdfReadError, extract_pdf
from app.services.query_engine import prime_dataset
from app.services.storage import StorageError, read_pdf

logger = logging.getLogger(__name__)

# Referências às tarefas em andamento (sem isso o asyncio pode descartá-las).
_tasks: set[asyncio.Task] = set()
_tasks_by_owner: dict[tuple[str, uuid.UUID], set[asyncio.Task]] = {}
_validation_requested: set[uuid.UUID] = set()
_queries_requested: set[uuid.UUID] = set()


QUERIES_MESSAGE = "Gerando as buscas nas bases de dados"
QUERIES_INTERRUPTED = (
    "As regras foram encontradas, mas a geração das buscas foi interrompida. "
    "Use “Gerar buscas” para tentar de novo."
)


def _start(coro, *, owner: tuple[str, uuid.UUID] | None = None) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    if owner is not None:
        _tasks_by_owner.setdefault(owner, set()).add(task)

        def finished(done: asyncio.Task) -> None:
            tasks = _tasks_by_owner.get(owner)
            if tasks is not None:
                tasks.discard(done)
                if not tasks:
                    _tasks_by_owner.pop(owner, None)

        task.add_done_callback(finished)


async def stop_analysis_work(document_ids: list[uuid.UUID], dataset_ids: list[uuid.UUID]) -> None:
    """Encerra as tarefas deste uso antes de apagar os bancos que elas poderiam recriar."""
    owners = {*(("document", i) for i in document_ids), *(("dataset", i) for i in dataset_ids)}
    _validation_requested.difference_update(document_ids)
    _queries_requested.difference_update(document_ids)
    while pending := {
        task for owner in owners for task in _tasks_by_owner.get(owner, ()) if not task.done()
    }:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


def start_processing(
    document_id: uuid.UUID,
    extracted: ExtractedDocument | None = None,
    *,
    source: SourceFile | None = None,
    title: str | None = None,
) -> None:
    _start(
        process_document(document_id, extracted, source=source, title=title),
        owner=("document", document_id),
    )


def start_dataset_processing(dataset_id: uuid.UUID, data: bytes | None = None) -> None:
    _start(process_dataset(dataset_id, data), owner=("dataset", dataset_id))


async def process_dataset(dataset_id: uuid.UUID, data: bytes | None = None) -> None:
    """Reaproveita o upload e publica o schema antes da interpretação semântica."""
    values: dict = {"status": "error"}
    try:
        with log_step(logger, "process_dataset", dataset_id=str(dataset_id)) as info:
            if data is None:
                data = await storage.read_file(storage.dataset_name(dataset_id))
            parsed = await asyncio.to_thread(parse_csv, data)
            size_bytes = len(data)
            data = None
            physical_columns = [c.to_dict() for c in parsed.columns]
            row_count = len(parsed.rows)
            # O cache recebe as mesmas linhas, sem baixar ou inferir o CSV novamente.
            await prime_dataset(dataset_id, size_bytes, physical_columns, parsed)
            encoding, delimiter = parsed.encoding, parsed.delimiter
            del parsed
            async with SessionLocal() as db:
                dataset = await db.get(Dataset, dataset_id)
                if dataset is None:
                    return
                name = dataset.name
                analysis_id = dataset.analysis_id
                dataset.columns = physical_columns
                dataset.row_count = row_count
                dataset.encoding = encoding
                dataset.delimiter = delimiter
                dataset.status_message = "Interpretando o significado das colunas com IA"
                await db.commit()
            columns, warning = await rule_validation.interpret(name, physical_columns)
            values = {
                "status": "ready",
                "status_message": warning,
                "encoding": encoding,
                "delimiter": delimiter,
                "row_count": row_count,
                "columns": columns,
            }
            info.update(rows=row_count, columns=len(columns))
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
            request_query_generation(document_id)


def request_query_generation(document_id: uuid.UUID) -> None:
    """Base nova: prepara consultas, sem validar registros ou concorrer com a extração."""
    _queries_requested.add(document_id)
    if any(not task.done() for task in _tasks_by_owner.get(("document", document_id), ())):
        return
    start_query_generation(document_id, overwrite=True)


def start_validation(
    document_id: uuid.UUID, *, refresh_columns: bool = False, reserved: bool = False
) -> None:
    _validation_requested.add(document_id)
    _start(
        _validate(document_id, refresh_columns=refresh_columns, reserved=reserved),
        owner=("document", document_id),
    )


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
        if not await _wait_for_datasets(document_id):
            return
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
    _start(
        _generate_queries(document_id, overwrite=overwrite, only_related=False),
        owner=("document", document_id),
    )


async def _generate_queries(document_id: uuid.UUID, *, overwrite: bool, only_related: bool) -> None:
    """Etapa das buscas. Uma falha aqui não perde as regras: o documento fica pronto, com
    o motivo em `status_message`."""
    await _set_status(document_id, "extracting_rules", QUERIES_MESSAGE)
    message: str | None = None
    try:
        if not await _wait_for_datasets(document_id):
            return
        _queries_requested.discard(document_id)
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
    await _set_status(document_id, "ready", message)


async def _wait_for_datasets(document_id: uuid.UUID) -> bool:
    """A extração pode sobrepor a interpretação; os vereditos aguardam as bases."""
    waiting = False
    while True:
        async with SessionLocal() as db:
            analysis_id = await db.scalar(
                select(Document.analysis_id).where(Document.id == document_id)
            )
            if analysis_id is None:
                return False
            pending = await db.scalar(
                select(Dataset.id)
                .where(Dataset.analysis_id == analysis_id, Dataset.status == "processing")
                .limit(1)
            )
        if pending is None:
            return True
        if not waiting:
            await _set_status(
                document_id, "extracting_rules", "Aguardando a interpretação das bases"
            )
            waiting = True
        await asyncio.sleep(0.5)


async def _set_status(document_id: uuid.UUID, status: str, message: str | None = None) -> None:
    async with SessionLocal() as db:
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=status, status_message=message)
        )
        await db.commit()
    if status == "ready" and document_id in _queries_requested:
        _queries_requested.discard(document_id)
        start_query_generation(document_id, overwrite=True)
    elif status == "ready" and document_id in _validation_requested:
        start_validation(document_id)
    elif status == "error":
        _validation_requested.discard(document_id)
        _queries_requested.discard(document_id)


async def process_document(
    document_id: uuid.UUID,
    extracted: ExtractedDocument | None = None,
    *,
    source: SourceFile | None = None,
    title: str | None = None,
) -> None:
    """Converte o original recebido, grava palavras e extrai regras em segundo plano."""
    try:
        converted = None
        async with SessionLocal() as db:
            doc = await db.get(Document, document_id)
            if doc is None:
                return
            checkpoint = doc.extraction_checkpoint
            storage_path = doc.storage_path
            analysis_id, initial_title = doc.analysis_id, doc.title
        if extracted is None:
            with log_step(logger, "convert_document", document_id=str(document_id)) as info:
                if storage_path is None:
                    converted = await document_upload.convert_source(
                        document_id, source, title=title
                    )
                    source = None
                    extracted = converted.extracted
                    storage_path = await storage.save_pdf(document_id, converted.pdf)
                else:
                    data = await read_pdf(document_id)
                    extracted = await asyncio.to_thread(extract_pdf, data)
                    del data
                info["pages"] = len(extracted.pages)
                info["chars"] = len(extracted.full_text)

        async with SessionLocal() as db:
            values = dict(
                full_text=extracted.full_text,
                page_count=len(extracted.pages),
                storage_path=storage_path,
                status="extracting_rules",
                status_message=None,
            )
            if converted is not None:
                values.update(title=converted.title[:200], source_type=converted.source_type)
            saved_id = await db.scalar(
                update(Document)
                .where(Document.id == document_id)
                .values(**values)
                .returning(Document.id)
            )
            if saved_id is None:
                await db.rollback()
                await storage.delete_pdf(document_id)
                return
            if converted is not None:
                await db.execute(
                    update(Analysis)
                    .where(Analysis.id == analysis_id, Analysis.title == initial_title)
                    .values(title=converted.title[:200])
                )
            # Retomar após reinício não duplica páginas/palavras já persistidas.
            await db.execute(delete(Word).where(Word.document_id == document_id))
            await db.execute(delete(Page).where(Page.document_id == document_id))
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

        full_text = extracted.full_text
        extracted = None
        converted = None

        async def save_checkpoint(value: dict) -> None:
            async with SessionLocal() as db:
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        extraction_checkpoint=value,
                    )
                )
                await db.commit()

        async def progress(done: int, total: int) -> None:
            await _set_status(
                document_id, "extracting_rules", f"Pacotes concluidos: {done} de {total}"
            )

        if not await _wait_for_datasets(document_id):
            return
        async with SessionLocal() as db:
            analysis_id = await db.scalar(
                select(Document.analysis_id).where(Document.id == document_id)
            )
            datasets = await rule_queries.analysis_datasets(db, analysis_id) if analysis_id else []
        dataset_ids = {d.name: d.id for d in datasets}

        with log_step(logger, "extract_rules", document_id=str(document_id)) as info:
            found = await llm.extract_rules(
                full_text,
                on_progress=progress,
                datasets=rule_queries.dataset_prompts(datasets),
                checkpoint=checkpoint,
                on_checkpoint=save_checkpoint,
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
                    excerpt=full_text[r.start : r.end],
                    char_start=r.start,
                    char_end=r.end,
                    origin="ia",
                    dataset_ids=[dataset_ids[n] for n in r.datasets if n in dataset_ids],
                )
                for r in rules
            )
            await db.commit()

        if datasets:
            await _generate_queries(document_id, overwrite=False, only_related=False)
        else:
            await _set_status(document_id, "ready")
    except (PdfReadError, StorageError, ConversionError) as exc:
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
    """Retoma os originais e PDFs persistidos sem exigir novo upload após reinício."""
    async with SessionLocal() as db:
        pending = (await db.scalars(select(Dataset.id).where(Dataset.status == "processing"))).all()
        documents = (
            await db.execute(
                select(Document.id, exists().where(Rule.document_id == Document.id)).where(
                    Document.status.in_(("processing", "extracting_rules"))
                )
            )
        ).all()
        await db.execute(
            update(Rule)
            .where(
                Rule.document_id.in_(
                    select(Document.id).where(Document.status == "extracting_rules")
                )
            )
            .values(validation=None)
        )
        await db.commit()
    for dataset_id in pending:
        start_dataset_processing(dataset_id)
    for document_id, has_rules in documents:
        if has_rules:
            _start(
                _generate_queries(document_id, overwrite=False, only_related=False),
                owner=("document", document_id),
            )
        else:
            start_processing(document_id)
