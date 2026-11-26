"""Documentos, regras e conversa sobre o documento."""

import json
import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sse_starlette.sse import EventSourceResponse

from app.api.deps import SessionDep, UserDep
from app.api.v1.analyses import owned_analysis
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError, PayloadTooLargeError
from app.db.models import (
    Analysis,
    Conversation,
    Dataset,
    Document,
    Message,
    Rule,
    RuleQuery,
    User,
    Word,
)
from app.db.session import SessionLocal
from app.processing.ai import llm
from app.processing.datasets.duckdb_sql import readable_sql
from app.processing.datasets.query_engine import QueryError
from app.processing.documents import document_upload, safe_fetch
from app.processing.documents.converters import (
    ConversionError,
    SourceFile,
    UnsupportedFormatError,
)
from app.processing.documents.converters.text import title_from_text
from app.processing.documents.highlights import page_range, rule_boxes
from app.processing.documents.text_match import find_excerpt
from app.processing.pipeline import ingest
from app.processing.rules import rule_queries, rule_validation
from app.processing.shared import storage
from app.schemas.common import error_responses
from app.schemas.documents import (
    CitedRule,
    DocumentOut,
    ExcerptAnalysisIn,
    ExcerptAnalysisOut,
    MessageIn,
    MessageOut,
    QueryPreviewOut,
    QuerySuggestionIn,
    QuerySuggestionOut,
    RuleCreateIn,
    RuleOut,
    RuleProposal,
    RuleUpdateIn,
    TextDocumentIn,
    UrlDocumentIn,
)
from app.schemas.queries import RecordsOut, RuleQueryOut, StructuredQuery
from app.schemas.validation import RecordVerdict, ValidationRecordsOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documentos"])

# Uma semana: o mesmo documento nunca recebe outro PDF (ver `get_document_file`).
PDF_CACHE_CONTROL = "private, max-age=604800, immutable"

CITATION = re.compile(r"\[(R\d+(?:\s*,\s*R\d+)*)\]")
CITATION_WITH_SPACE = re.compile(r"\s*\[R\d+(?:\s*,\s*R\d+)*\]")
DEFAULT_ANALYSIS_TITLE = "Nova análise"


async def _owned_document(db: SessionDep, document_id: uuid.UUID, user: User) -> Document:
    doc = await db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise NotFoundError("Documento não encontrado.")
    return doc


async def _owned_rule(db: SessionDep, rule_id: uuid.UUID, user: User) -> Rule:
    rule = await db.get(Rule, rule_id)
    if rule is None:
        raise NotFoundError("Regra não encontrada.")
    await _owned_document(db, rule.document_id, user)
    return rule


def _query_out(q: RuleQuery, dataset_names: dict[uuid.UUID, str]) -> RuleQueryOut:
    try:
        query = StructuredQuery.model_validate(q.query)
    except ValidationError:
        # Não deveria acontecer (a busca é saneada antes de gravar), mas não derruba a lista.
        query = StructuredQuery(dataset=str(q.query.get("dataset") or "?"), conditions=[])
    dataset_name = dataset_names.get(q.dataset_id) if q.dataset_id else None
    return RuleQueryOut(
        id=q.id,
        dataset_id=q.dataset_id,
        dataset_name=dataset_name,
        query=query,
        sql=q.sql,
        sql_parameters=q.sql_parameters or {},
        sql_display=readable_sql(query, dataset_name),
        origin=q.origin,
        state=q.state,
        error=q.error,
        match_count=q.match_count,
        executed_at=q.executed_at,
        verdict=q.verdict,
        verdict_details=q.verdict_details,
    )


async def _rules_out(db: SessionDep, document_id: uuid.UUID, rules: list[Rule]) -> list[RuleOut]:
    boxes = await rule_boxes(db, document_id, {r.id: (r.char_start, r.char_end) for r in rules})
    queries: dict[uuid.UUID, RuleQuery] = {}
    dataset_names: dict[uuid.UUID, str] = {}
    if rules:
        queries = {
            q.rule_id: q
            for q in await db.scalars(
                select(RuleQuery).where(RuleQuery.rule_id.in_([r.id for r in rules]))
            )
        }
        used = {q.dataset_id for q in queries.values() if q.dataset_id}
        if used:
            dataset_names = {
                row.id: row.name
                for row in await db.execute(
                    select(Dataset.id, Dataset.name).where(Dataset.id.in_(used))
                )
            }
    return [
        RuleOut(
            id=r.id,
            type=r.type,
            status=r.status,
            summary=r.summary,
            excerpt=r.excerpt,
            comment=r.comment,
            origin=r.origin,
            category=r.category,
            interpretation=r.interpretation,
            conversation=r.conversation or [],
            page=boxes[r.id][0]["page"] if boxes.get(r.id) else None,
            boxes=boxes.get(r.id, []),
            dataset_ids=r.dataset_ids or [],
            validation=r.validation,
            query=_query_out(queries[r.id], dataset_names) if r.id in queries else None,
        )
        for r in rules
    ]


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------


async def _target_analysis(db: SessionDep, user: User, analysis_id: uuid.UUID | None) -> Analysis:
    if analysis_id is not None:
        return await owned_analysis(db, analysis_id, user)
    analysis = Analysis(user_id=user.id, title=DEFAULT_ANALYSIS_TITLE)
    db.add(analysis)
    await db.flush()
    return analysis


async def _create_document(
    db: SessionDep,
    user: User,
    analysis_id: uuid.UUID | None,
    source: SourceFile,
    *,
    source_url: str | None = None,
    title: str | None = None,
) -> DocumentOut:
    """Persiste o original e confirma o envio antes da conversão e extração."""
    try:
        source_type = document_upload.validate_source(source)
    except UnsupportedFormatError as exc:
        raise AppError(str(exc), code="unsupported_format", status_code=422) from exc
    except ConversionError as exc:
        raise AppError(str(exc), code="conversion_error", status_code=422) from exc
    user_id = user.id
    analysis = await _target_analysis(db, user, analysis_id)
    target_id = analysis.id
    title_override = title
    title = title or (source.filename if source_type == "pdf" else source.stem) or "Documento"
    title = title[:200]
    has_documents = await db.scalar(select(func.count()).where(Document.analysis_id == target_id))
    if analysis.title == DEFAULT_ANALYSIS_TITLE and not has_documents:
        analysis.title = title
    # Release the connection before network/disk IO. The original is durable before
    # publishing a processing document, so restart recovery can always resume it.
    await db.commit()
    document_id = uuid.uuid4()
    try:
        await document_upload.save_source(document_id, source, title=title_override)
    except storage.StorageError as exc:
        raise AppError(str(exc), code="storage_error", status_code=502) from exc
    doc = Document(
        id=document_id,
        user_id=user_id,
        analysis_id=target_id,
        title=title,
        source_type=source_type,
        source_url=source_url,
        mode="assistant",
        status="processing",
    )
    persisted = False
    try:
        db.add(doc)
        await db.commit()
        persisted = True
        await db.refresh(doc)
        result = DocumentOut.model_validate(doc)
        await db.commit()
    except Exception:
        await db.rollback()
        if not persisted:
            try:
                await storage.delete_files(storage.document_files(document_id))
            except Exception:
                logger.exception(
                    "document_source_cleanup_failed", extra={"document_id": str(document_id)}
                )
        raise
    ingest.start_processing(document_id, source=source, title=title_override)
    return result


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia um arquivo (PDF, HTML ou TXT); conversão e extração em segundo plano",
    description=(
        "O original é salvo antes da resposta 202. Conversão e leitura acontecem em segundo "
        "plano: PDF sem texto ou HTML vazio resultam em status `error`. Formatos não "
        "suportados voltam com 422. O PDF fica disponível após a conversão. Sem `analysis_id`, "
        "o documento ganha uma análise só dele."
    ),
    responses=error_responses(401, 404, 413, 422),
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Arquivo PDF, HTML ou TXT")],
    user: UserDep,
    db: SessionDep,
    analysis_id: Annotated[uuid.UUID | None, Form(description="Análise do documento")] = None,
) -> DocumentOut:
    limit = get_settings().max_upload_bytes
    await db.commit()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLargeError(
            f"O arquivo passa do limite de {get_settings().max_upload_mb} MB."
        )
    content_type = (file.content_type or "").split(";")[0].strip().lower() or None
    source = SourceFile(data=data, filename=file.filename, content_type=content_type)
    return await _create_document(db, user, analysis_id, source)


@router.post(
    "/documents/text",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cria um documento a partir de texto colado",
    responses=error_responses(401, 404, 422),
)
async def create_text_document(body: TextDocumentIn, user: UserDep, db: SessionDep) -> DocumentOut:
    limit = get_settings().max_pasted_chars
    if len(body.content) > limit:
        raise AppError(
            f"O texto passa do limite de {limit:_} caracteres.".replace("_", "."),
            code="text_too_long",
            status_code=422,
        )
    source = SourceFile(
        data=body.content.encode("utf-8"), content_type="text/plain", charset="utf-8"
    )
    title = body.title or title_from_text(body.content)
    return await _create_document(db, user, body.analysis_id, source, title=title)


@router.post(
    "/documents/url",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Baixa um documento (PDF ou página HTML) a partir de um link",
    description=(
        "Só http/https. Endereços internos ou privados são bloqueados, inclusive depois de "
        "redirecionamentos. O download tem tempo e tamanho limitados; falhas voltam com "
        "422 e uma mensagem explicando o motivo (`fetch_error`)."
    ),
    responses=error_responses(401, 404, 413, 422),
)
async def create_url_document(body: UrlDocumentIn, user: UserDep, db: SessionDep) -> DocumentOut:
    settings = get_settings()
    if body.analysis_id is not None:
        await owned_analysis(db, body.analysis_id, user)
    await db.commit()
    try:
        fetched = await safe_fetch.fetch_url(
            body.url,
            max_bytes=settings.max_upload_bytes,
            time_limit=settings.url_fetch_timeout_seconds,
        )
    except safe_fetch.FetchError as exc:
        raise AppError(str(exc), code="fetch_error", status_code=422) from exc
    source = SourceFile(
        data=fetched.data,
        filename=fetched.filename,
        content_type=fetched.content_type,
        charset=fetched.charset,
    )
    return await _create_document(db, user, body.analysis_id, source, source_url=fetched.final_url)


@router.get("/documents", summary="Documentos do usuário, do mais recente ao mais antigo")
async def list_documents(user: UserDep, db: SessionDep) -> list[DocumentOut]:
    docs = await db.scalars(
        select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
    )
    return [DocumentOut.model_validate(d) for d in docs]


@router.post(
    "/documents/{document_id}/resume",
    status_code=202,
    summary="Lê de novo o documento interrompido, sem reenviar o arquivo",
)
async def resume_document(document_id: uuid.UUID, user: UserDep, db: SessionDep) -> DocumentOut:
    doc = await _owned_document(db, document_id, user)
    claimed = await db.scalar(
        update(Document)
        .where(Document.id == doc.id, Document.status == "error")
        .values(status="processing", status_message="Retomando a leitura do documento")
        .returning(Document.id)
    )
    if claimed is None:
        raise ConflictError("Somente documentos interrompidos podem ser retomados.")
    await db.commit()
    await db.refresh(doc)
    ingest.start_processing(doc.id)
    return DocumentOut.model_validate(doc)


@router.get(
    "/documents/{document_id}", summary="Status do documento", responses=error_responses(404)
)
async def get_document(document_id: uuid.UUID, user: UserDep, db: SessionDep) -> DocumentOut:
    return DocumentOut.model_validate(await _owned_document(db, document_id, user))


@router.get(
    "/documents/{document_id}/file",
    summary="O PDF original",
    response_class=Response,
    responses=error_responses(404),
)
async def get_document_file(
    document_id: uuid.UUID, user: UserDep, db: SessionDep, request: Request
) -> Response:
    doc = await _owned_document(db, document_id, user)
    stored_id = doc.id
    await db.commit()
    # O PDF é gravado uma única vez, na conversão: o navegador pode guardá-lo. `private`
    # impede caches compartilhados (proxies) de guardar um arquivo de um usuário logado.
    headers = {"Cache-Control": PDF_CACHE_CONTROL, "ETag": f'"{stored_id}"'}
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    try:
        data = await storage.read_pdf(stored_id)
    except storage.StorageError as exc:
        raise NotFoundError("Arquivo não encontrado.") from exc
    return Response(data, media_type="application/pdf", headers=headers)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui o documento, as regras e a conversa",
)
async def delete_document(document_id: uuid.UUID, user: UserDep, db: SessionDep) -> None:
    doc = await _owned_document(db, document_id, user)
    await db.delete(doc)
    await db.commit()
    await storage.delete_pdf(document_id)


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}/rules", summary="Regras do documento, na ordem do texto")
async def list_rules(document_id: uuid.UUID, user: UserDep, db: SessionDep) -> list[RuleOut]:
    await _owned_document(db, document_id, user)
    rules = (
        await db.scalars(
            select(Rule).where(Rule.document_id == document_id).order_by(Rule.char_start)
        )
    ).all()
    return await _rules_out(db, document_id, list(rules))


async def _ready_document(db: SessionDep, document_id: uuid.UUID, user: User) -> Document:
    doc = await _owned_document(db, document_id, user)
    if doc.status != "ready" or not doc.full_text:
        raise AppError(
            "Aguarde o documento terminar de ser lido.", code="not_ready", status_code=409
        )
    return doc


async def _locate_excerpt(
    db: SessionDep, doc: Document, page: int, excerpt: str
) -> tuple[int, int, tuple[int, int]]:
    """Posição do trecho grifado em `full_text` e o intervalo da página onde ele está."""
    bounds = await page_range(db, doc.id, page)
    span = bounds and find_excerpt(doc.full_text[: bounds[1]], excerpt, bounds[0])
    if not span:
        raise AppError(
            "Não encontrei esse trecho no texto da página. Tente selecionar de novo.",
            code="excerpt_not_found",
            status_code=422,
        )
    return span[0], span[1], bounds


def _invalid_query(exc: Exception) -> AppError:
    return AppError(str(exc), code="invalid_query", status_code=422)


@router.post(
    "/documents/{document_id}/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Aprova e salva a regra de um trecho grifado (com a busca, se verificável)",
    description=(
        "É a única forma de uma regra entrar no banco: a pessoa revisou a proposta. "
        "Em `category = csv` a busca é validada contra o schema da base e a SQL é "
        "preparada (sem executar); em `geral` a regra fica registrada sem busca."
    ),
    responses=error_responses(404, 409, 422),
)
async def create_rule(
    document_id: uuid.UUID, body: RuleCreateIn, user: UserDep, db: SessionDep
) -> RuleOut:
    doc = await _ready_document(db, document_id, user)
    start, end, _ = await _locate_excerpt(db, doc, body.page, body.excerpt)
    rule_query: RuleQuery | None = None
    if body.category == "csv":
        if body.query is None:
            raise AppError(
                "Uma regra verificável no CSV precisa de uma busca.",
                code="invalid_query",
                status_code=422,
            )
        datasets = await rule_queries.analysis_datasets(db, doc.analysis_id)
        rule_query = RuleQuery(
            query=body.query.model_dump(mode="json"),
            origin=body.origin,
            state="pendente",
            matched_rows=[],
        )
        try:
            rule_queries.prepare_query(rule_query, datasets)
        except QueryError as exc:
            raise _invalid_query(exc) from exc
    rule = Rule(
        document_id=document_id,
        type=body.type,
        summary=body.summary,
        excerpt=doc.full_text[start:end],
        char_start=start,
        char_end=end,
        origin=body.origin,
        status="validada",
        category=body.category,
        interpretation=body.interpretation,
        conversation=[m.model_dump() for m in body.messages],
        dataset_ids=[rule_query.dataset_id] if rule_query and rule_query.dataset_id else [],
    )
    db.add(rule)
    await db.flush()
    if rule_query is not None:
        rule_query.rule_id = rule.id
        db.add(rule_query)
    await db.commit()
    await db.refresh(rule)
    return (await _rules_out(db, document_id, [rule]))[0]


@router.patch("/rules/{rule_id}", summary="Atualiza situação, tipo, resumo ou comentário")
async def update_rule(
    rule_id: uuid.UUID, body: RuleUpdateIn, user: UserDep, db: SessionDep
) -> RuleOut:
    rule = await _owned_rule(db, rule_id, user)
    doc = await _owned_document(db, rule.document_id, user)
    if doc.status != "ready":
        raise ConflictError("Aguarde a verificação terminar antes de editar a regra.")
    changes = body.model_dump(exclude_unset=True)
    if any(
        changes.get(key) is not None and changes[key] != getattr(rule, key)
        for key in ("type", "summary")
    ):
        rule.validation = None
    if rule.status == "rejeitada" and changes.get("status") not in (None, "rejeitada"):
        rule.validation = None
    if changes.get("status") == "rejeitada":
        rule.validation = rule_validation.result("ignorada", "Regra rejeitada na revisão humana.")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None or field == "comment":
            setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return (await _rules_out(db, rule.document_id, [rule]))[0]


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Exclui a regra")
async def delete_rule(rule_id: uuid.UUID, user: UserDep, db: SessionDep) -> Response:
    rule = await _owned_rule(db, rule_id, user)
    doc = await _owned_document(db, rule.document_id, user)
    if doc.status != "ready":
        raise ConflictError("Aguarde a verificação terminar antes de excluir a regra.")
    await db.execute(delete(Rule).where(Rule.id == rule.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Buscas nas bases de dados
# ---------------------------------------------------------------------------


async def _rule_query(db: SessionDep, rule_id: uuid.UUID) -> RuleQuery | None:
    return await db.scalar(select(RuleQuery).where(RuleQuery.rule_id == rule_id))


async def _rule_datasets(db: SessionDep, rule: Rule) -> list[Dataset]:
    analysis_id = await db.scalar(
        select(Document.analysis_id).where(Document.id == rule.document_id)
    )
    return await rule_queries.analysis_datasets(db, analysis_id)


@router.put(
    "/rules/{rule_id}/query",
    summary="Define (ou corrige) e prepara a SQL da regra, sem executar",
    description=(
        "A busca é validada contra o schema da base antes de ser gravada; uma busca inválida "
        "volta com 422 (`invalid_query`) e a mensagem do problema, sem alterar a atual."
    ),
    responses=error_responses(404, 422),
)
async def set_rule_query(
    rule_id: uuid.UUID, body: StructuredQuery, user: UserDep, db: SessionDep
) -> RuleOut:
    rule = await _owned_rule(db, rule_id, user)
    datasets = await _rule_datasets(db, rule)
    await db.commit()
    rule_query = await _rule_query(db, rule.id)
    # Valida antes de modificar a consulta existente.
    try:
        compiled = rule_queries.compile_query(body, rule_queries.dataset_refs(datasets))
    except QueryError as exc:
        raise AppError(str(exc), code="invalid_query", status_code=422) from exc
    if rule_query is None:
        rule_query = RuleQuery(rule_id=rule.id, query={}, origin="manual", matched_rows=[])
        db.add(rule_query)
    rule_queries.set_query(rule_query, compiled.normalized.model_dump(mode="json"), "manual")
    rule_queries.prepare_query(rule_query, datasets)
    if compiled.dataset.id not in (rule.dataset_ids or []):
        rule.dataset_ids = [*(rule.dataset_ids or []), compiled.dataset.id]
    rule.category = "csv"
    await db.commit()
    await db.refresh(rule)
    return (await _rules_out(db, rule.document_id, [rule]))[0]


@router.post(
    "/rules/{rule_id}/query/run",
    summary="Roda de novo a busca da regra (ex.: depois de reenviar a base)",
    responses=error_responses(404, 409),
)
async def run_rule_query(rule_id: uuid.UUID, user: UserDep, db: SessionDep) -> RuleOut:
    rule = await _owned_rule(db, rule_id, user)
    rule_query = await _rule_query(db, rule.id)
    if rule_query is None:
        raise ConflictError("Esta regra ainda não tem busca.", code="no_query")
    datasets = await _rule_datasets(db, rule)
    await db.commit()
    await rule_queries.execute(rule_query, datasets)
    await db.commit()
    return (await _rules_out(db, rule.document_id, [rule]))[0]


@router.delete(
    "/rules/{rule_id}/query",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a busca da regra (ela passa para as regras gerais)",
    responses=error_responses(404),
)
async def delete_rule_query(rule_id: uuid.UUID, user: UserDep, db: SessionDep) -> Response:
    rule = await _owned_rule(db, rule_id, user)
    await db.execute(delete(RuleQuery).where(RuleQuery.rule_id == rule.id))
    rule.category = "geral"
    rule.validation = None
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/rules/{rule_id}/records",
    summary="Registros da base encontrados pela busca da regra, paginados",
    responses=error_responses(404, 409),
)
async def list_rule_records(
    rule_id: uuid.UUID,
    user: UserDep,
    db: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> RecordsOut:
    rule = await _owned_rule(db, rule_id, user)
    rule_query = await _rule_query(db, rule.id)
    if rule_query is None or rule_query.state == "erro":
        raise ConflictError("Esta regra não tem uma busca válida.", code="no_query")
    datasets = await _rule_datasets(db, rule)
    await db.commit()
    try:
        result = await rule_queries.execute_page(rule_query, datasets, offset=offset, limit=limit)
    except (QueryError, ValidationError) as exc:
        rule_queries.mark_failed(rule_query, str(exc))
        await db.commit()
        raise ConflictError(str(exc), code="no_query") from exc
    await db.commit()
    result.query = _query_out(rule_query, {result.dataset_id: result.dataset_name})
    return result


# ---------------------------------------------------------------------------
# Trecho grifado: conversa com a IA e prévia da busca (nada é salvo aqui)
# ---------------------------------------------------------------------------


def _excerpt_context(page_text: str, offset: int, start: int, end: int) -> str:
    """Texto da página em volta do trecho, limitado para não estourar o prompt."""
    budget = llm.EXCERPT_CONTEXT_CHARS
    if len(page_text) <= budget:
        return page_text
    middle = (start + end) // 2 - offset
    left = max(0, min(middle - budget // 2, len(page_text) - budget))
    return page_text[left : left + budget]


async def _proposal_query(
    query: StructuredQuery | None, datasets: list[Dataset]
) -> tuple[StructuredQuery | None, str | None, int | None, str | None]:
    """Valida e conta a busca proposta. Inválida, ela volta como está, com o erro."""
    if query is None:
        return None, None, None, None
    try:
        compiled, count = await rule_queries.count_matches(query, datasets)
    except QueryError as exc:
        return query, None, None, str(exc)
    sql = readable_sql(compiled.normalized, compiled.dataset.name)
    return compiled.normalized, sql, count, None


async def _previous_rules(db: SessionDep, doc: Document) -> list[str]:
    """Regras já aprovadas no documento, resumidas para a IA manter a coerência."""
    rules = (
        await db.scalars(select(Rule).where(Rule.document_id == doc.id).order_by(Rule.char_start))
    ).all()
    if not rules:
        return []
    starts = (
        await db.execute(
            select(Word.page, func.min(Word.char_start))
            .where(Word.document_id == doc.id)
            .group_by(Word.page)
            .order_by(Word.page)
        )
    ).all()

    def page_of(char: int) -> int:
        current = 1
        for page, start in starts:
            if start <= char:
                current = page
        return current

    lines = []
    budget = llm.PREVIOUS_RULES_CHARS
    for r in rules:
        excerpt = " ".join(r.excerpt.split())
        line = (
            f"- p. {page_of(r.char_start)} · {r.category} · {r.type} · {r.status}: {r.summary}\n"
            f"  Trecho: “{excerpt[:300]}{'…' if len(excerpt) > 300 else ''}”"
        )
        if r.interpretation:
            line += f"\n  Interpretação: {' '.join(r.interpretation.split())[:400]}"
        budget -= len(line)
        if budget < 0:
            lines.append(f"- (mais {len(rules) - len(lines)} regras não listadas)")
            break
        lines.append(line)
    return lines


@router.post(
    "/documents/{document_id}/excerpt-analysis",
    summary="A IA analisa o trecho grifado e propõe a regra (sem salvar)",
    description=(
        "Classifica o trecho como regra verificável nas bases (`csv`) ou não (`geral`) e, "
        "se verificável, propõe a busca, já validada e contada nos registros. Envie a "
        "conversa em `messages` para pedir ajustes; a proposta só entra no banco pela "
        "aprovação (POST /documents/{id}/rules)."
    ),
    responses=error_responses(404, 409, 422, 503),
)
async def analyze_excerpt(
    document_id: uuid.UUID, body: ExcerptAnalysisIn, user: UserDep, db: SessionDep
) -> ExcerptAnalysisOut:
    doc = await _ready_document(db, document_id, user)
    start, end, (page_start, page_end) = await _locate_excerpt(db, doc, body.page, body.excerpt)
    if body.messages and body.messages[-1].role != "user":
        raise AppError(
            "A conversa deve terminar com uma mensagem sua.",
            code="invalid_messages",
            status_code=422,
        )
    datasets = await rule_queries.analysis_datasets(db, doc.analysis_id)
    page_text = doc.full_text[page_start:page_end]
    previous = await _previous_rules(db, doc)
    # A conexão não fica presa enquanto a IA responde.
    await db.commit()
    prompt = llm.ExcerptPrompt(
        excerpt=doc.full_text[start:end],
        page=body.page,
        context=_excerpt_context(page_text, page_start, start, end),
        datasets=rule_queries.dataset_prompts(datasets),
        history=[m.model_dump() for m in body.messages],
        current=body.current.model_dump(mode="json") if body.current else None,
        previous_rules=previous,
    )
    try:
        answer = await llm.analyze_excerpt(prompt)
    except llm.LlmUnavailableError as exc:
        raise AppError(str(exc), code="llm_unavailable", status_code=503) from exc
    except llm.LlmApiError as exc:
        raise AppError(str(exc), code="llm_error", status_code=503) from exc

    raw = None
    if answer.query is not None:
        try:
            raw = StructuredQuery.model_validate(answer.query)
        except ValidationError:
            raw = None
    query, sql, count, error = await _proposal_query(raw, datasets)
    if answer.query is not None and raw is None:
        error = "A busca proposta pela IA está num formato inválido. Monte-a no editor."
    verifiable = answer.verifiable and answer.query is not None
    return ExcerptAnalysisOut(
        reply=answer.reply or answer.reason,
        proposal=RuleProposal(
            is_rule=answer.is_rule,
            category="csv" if verifiable else "geral",
            type=answer.type,
            summary=answer.summary or " ".join(body.excerpt.split())[:150],
            interpretation=answer.interpretation,
            reason=answer.reason,
            query=query if verifiable else None,
            sql_display=sql if verifiable else None,
            match_count=count if verifiable else None,
            query_error=error if verifiable else None,
        ),
    )


@router.post(
    "/documents/{document_id}/query-suggestion",
    summary="A IA gera as condições de busca no CSV para a regra revisada (sem salvar)",
    description=(
        "Usado no botão “Gerar condições de busca” da revisão, depois da conversa com a IA. "
        "Envia o trecho, a conversa e a regra como está na tela; a busca volta validada e "
        "contada, ou com `query_error` para corrigir no editor. Sem bases prontas: 409 "
        "(`no_datasets`)."
    ),
    responses=error_responses(404, 409, 422, 503),
)
async def suggest_query(
    document_id: uuid.UUID, body: QuerySuggestionIn, user: UserDep, db: SessionDep
) -> QuerySuggestionOut:
    doc = await _ready_document(db, document_id, user)
    start, end, (page_start, page_end) = await _locate_excerpt(db, doc, body.page, body.excerpt)
    datasets = await rule_queries.analysis_datasets(db, doc.analysis_id)
    if not datasets:
        raise ConflictError(
            "Não há bases prontas nesta análise. Envie um CSV para gerar a busca.",
            code="no_datasets",
        )
    page_text = doc.full_text[page_start:page_end]
    previous = await _previous_rules(db, doc)
    await db.commit()
    prompt = llm.ExcerptPrompt(
        excerpt=doc.full_text[start:end],
        page=body.page,
        context=_excerpt_context(page_text, page_start, start, end),
        datasets=rule_queries.dataset_prompts(datasets),
        history=[m.model_dump() for m in body.messages],
        current=body.current.model_dump(mode="json") if body.current else None,
        previous_rules=previous,
    )
    try:
        answer = await llm.suggest_query(prompt)
    except llm.LlmUnavailableError as exc:
        raise AppError(str(exc), code="llm_unavailable", status_code=503) from exc
    except llm.LlmApiError as exc:
        raise AppError(str(exc), code="llm_error", status_code=503) from exc

    raw = None
    error = None
    if answer.query is not None:
        try:
            raw = StructuredQuery.model_validate(answer.query)
        except ValidationError:
            error = "A busca gerada pela IA está num formato inválido. Monte-a no editor."
    query, sql, count, query_error = await _proposal_query(raw, datasets)
    return QuerySuggestionOut(
        reply=answer.reply or "A IA não conseguiu montar a busca com as bases disponíveis.",
        query=query,
        sql_display=sql,
        match_count=count,
        query_error=error or query_error,
    )


@router.post(
    "/documents/{document_id}/query-preview",
    summary="Valida a busca revisada e conta os registros (sem salvar)",
    description=(
        "Usado na revisão da proposta: a busca inválida volta com 422 (`invalid_query`) e "
        "a mensagem do problema."
    ),
    responses=error_responses(404, 422),
)
async def preview_query(
    document_id: uuid.UUID, body: StructuredQuery, user: UserDep, db: SessionDep
) -> QueryPreviewOut:
    doc = await _owned_document(db, document_id, user)
    datasets = await rule_queries.analysis_datasets(db, doc.analysis_id)
    await db.commit()
    try:
        compiled, count = await rule_queries.count_matches(body, datasets)
    except QueryError as exc:
        raise _invalid_query(exc) from exc
    return QueryPreviewOut(
        query=compiled.normalized,
        dataset_id=compiled.dataset.id,
        sql_display=readable_sql(compiled.normalized, compiled.dataset.name),
        match_count=count,
    )


# ---------------------------------------------------------------------------
# Verificação de cumprimento (independente da revisão humana e das buscas manuais)
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/validation",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Interpreta as colunas e verifica todas as regras do documento nas bases",
    responses=error_responses(404, 409, 503),
)
async def validate_document(
    document_id: uuid.UUID,
    user: UserDep,
    db: SessionDep,
    refresh_columns: bool = False,
) -> DocumentOut:
    doc = await _owned_document(db, document_id, user)
    if doc.status != "ready":
        raise ConflictError("Aguarde o documento terminar de ser analisado.", code="not_ready")
    if await rule_queries.analysis_datasets(db, doc.analysis_id):
        try:
            llm.ensure_configured()
        except llm.LlmUnavailableError as exc:
            raise AppError(str(exc), code="llm_unavailable", status_code=503) from exc
    reserved = await db.scalar(
        update(Document)
        .where(Document.id == document_id, Document.status == "ready")
        .values(status="extracting_rules", status_message="Validando todas as regras nas bases")
        .returning(Document.id)
    )
    if reserved is None:
        raise ConflictError("Uma verificação deste documento já está em andamento.")
    await db.commit()
    await db.refresh(doc)
    ingest.start_validation(document_id, refresh_columns=refresh_columns, reserved=True)
    return DocumentOut.model_validate(doc)


@router.get(
    "/rules/{rule_id}/validation/records",
    summary="Registros verificados, com resultado e evidência de cada linha",
    responses=error_responses(404, 409),
)
async def validation_records(
    rule_id: uuid.UUID,
    dataset_id: uuid.UUID,
    user: UserDep,
    db: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    verdict: RecordVerdict | None = None,
) -> ValidationRecordsOut:
    rule = await _owned_rule(db, rule_id, user)
    datasets = await _rule_datasets(db, rule)
    await db.commit()
    try:
        return await rule_validation.records(
            rule,
            datasets,
            dataset_id,
            offset=offset,
            limit=limit,
            verdict=verdict,
        )
    except (QueryError, ValidationError) as exc:
        message = (
            str(exc) if isinstance(exc, QueryError) else "O plano precisa ser gerado novamente."
        )
        raise ConflictError(message, code="no_validation") from exc


# ---------------------------------------------------------------------------
# Conversa
# ---------------------------------------------------------------------------


def _strip_citations(text: str) -> str:
    return CITATION_WITH_SPACE.sub("", text)


def _message_out(message: Message, rules_by_id: dict[uuid.UUID, Rule]) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=_strip_citations(message.content),
        citations=[
            CitedRule(id=r.id, type=r.type, summary=r.summary)
            for rid in message.rule_ids
            if (r := rules_by_id.get(rid))
        ],
        created_at=message.created_at,
    )


async def _conversation(db, document_id: uuid.UUID) -> Conversation:
    conv = await db.scalar(
        select(Conversation)
        .where(Conversation.document_id == document_id)
        .order_by(Conversation.created_at)
        .limit(1)
    )
    if conv is None:
        conv = Conversation(document_id=document_id)
        db.add(conv)
        await db.flush()
    return conv


@router.get("/documents/{document_id}/messages", summary="Histórico da conversa sobre o documento")
async def list_messages(document_id: uuid.UUID, user: UserDep, db: SessionDep) -> list[MessageOut]:
    await _owned_document(db, document_id, user)
    conv = await db.scalar(select(Conversation).where(Conversation.document_id == document_id))
    if conv is None:
        return []
    messages = (
        await db.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
        )
    ).all()
    rules = await db.scalars(select(Rule).where(Rule.document_id == document_id))
    by_id = {r.id: r for r in rules}
    return [_message_out(m, by_id) for m in messages]


@router.post(
    "/documents/{document_id}/messages",
    summary="Pergunta sobre o documento; a resposta chega por SSE",
    description=(
        "Eventos: `delta` ({text}) com pedaços da resposta, que podem conter marcadores "
        "de citação como [R3]; `done` (MessageOut) com a mensagem final, já sem os "
        "marcadores e com as regras citadas; `error` ({message})."
    ),
    responses=error_responses(404, 409, 422),
)
async def send_message(
    document_id: uuid.UUID, body: MessageIn, user: UserDep, db: SessionDep
) -> EventSourceResponse:
    doc = await _owned_document(db, document_id, user)
    if doc.status != "ready" or not doc.full_text:
        raise AppError(
            "Aguarde o documento terminar de ser lido.", code="not_ready", status_code=409
        )

    # Texto por página, para a IA poder citar a página.
    ranges = (
        await db.execute(
            select(Word.page, func.min(Word.char_start), func.max(Word.char_end))
            .where(Word.document_id == document_id)
            .group_by(Word.page)
            .order_by(Word.page)
        )
    ).all()
    pages = [(page, doc.full_text[s:e]) for page, s, e in ranges]
    page_starts = [(page, s) for page, s, _ in ranges]

    def page_of(char: int) -> int:
        current = 1
        for page, start in page_starts:
            if start <= char:
                current = page
        return current

    rules = (
        await db.scalars(
            select(Rule)
            .where(Rule.document_id == document_id, Rule.status != "rejeitada")
            .order_by(Rule.char_start)
        )
    ).all()
    refs = {f"R{i + 1}": r for i, r in enumerate(rules)}
    context = llm.document_context(
        doc.title,
        pages,
        [
            (ref, f"[{r.type}, {r.status}, p. {page_of(r.char_start)}] {r.summary} — “{r.excerpt}”")
            for ref, r in refs.items()
        ],
    )

    conv = await _conversation(db, document_id)
    previous = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(previous)]
    history.append({"role": "user", "content": body.content})
    db.add(Message(conversation_id=conv.id, role="user", content=body.content, rule_ids=[]))
    await db.commit()
    conversation_id = conv.id
    rules_by_id = {r.id: r for r in rules}

    async def events():
        parts: list[str] = []
        try:
            async for text in llm.stream_chat(context, history):
                parts.append(text)
                yield {"event": "delta", "data": json.dumps({"text": text}, ensure_ascii=False)}
        except llm.LlmUnavailableError as exc:
            yield {"event": "error", "data": json.dumps({"message": str(exc)}, ensure_ascii=False)}
            return
        except llm.LlmApiError as exc:
            logger.warning("chat_failed", extra={"document_id": str(document_id)})
            yield {"event": "error", "data": json.dumps({"message": str(exc)}, ensure_ascii=False)}
            return

        content = "".join(parts)
        cited: list[uuid.UUID] = []
        for group in CITATION.findall(content):
            for ref in re.findall(r"R\d+", group):
                rule = refs.get(ref)
                if rule and rule.id not in cited:
                    cited.append(rule.id)
        # Sessão própria: a da requisição pode já ter sido fechada durante o streaming.
        async with SessionLocal() as session:
            message = Message(
                conversation_id=conversation_id, role="assistant", content=content, rule_ids=cited
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
        out = _message_out(message, rules_by_id)
        yield {"event": "done", "data": out.model_dump_json()}

    return EventSourceResponse(events())
