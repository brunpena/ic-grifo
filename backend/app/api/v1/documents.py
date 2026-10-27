"""Documentos, regras e conversa sobre o documento."""

import asyncio
import json
import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
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
from app.schemas.common import error_responses
from app.schemas.documents import (
    CitedRule,
    DocumentOut,
    GenerateQueriesIn,
    MessageIn,
    MessageOut,
    RuleCreateIn,
    RuleOut,
    RuleUpdateIn,
    TextDocumentIn,
    UrlDocumentIn,
)
from app.schemas.queries import RecordRow, RecordsOut, RuleQueryOut, StructuredQuery
from app.schemas.validation import RecordVerdict, ValidationRecordsOut
from app.services import ingest, llm, rule_queries, rule_validation, safe_fetch, storage
from app.services.converters import (
    ConversionError,
    SourceFile,
    UnsupportedFormatError,
    registry,
)
from app.services.converters.text import title_from_text
from app.services.highlights import page_range, rule_boxes
from app.services.query_engine import QueryError, load_dataset
from app.services.text_match import find_excerpt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documentos"])

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
    return RuleQueryOut(
        id=q.id,
        dataset_id=q.dataset_id,
        dataset_name=dataset_names.get(q.dataset_id) if q.dataset_id else None,
        query=query,
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
    """Converte o conteúdo (qualquer formato do registro), guarda o PDF e começa a extração."""
    analysis = await _target_analysis(db, user, analysis_id)
    try:
        converted = await asyncio.to_thread(registry.convert, source)
    except UnsupportedFormatError as exc:
        raise AppError(str(exc), code="unsupported_format", status_code=422) from exc
    except ConversionError as exc:
        raise AppError(str(exc), code="conversion_error", status_code=422) from exc
    title = title or converted.title

    has_documents = await db.scalar(select(func.count()).where(Document.analysis_id == analysis.id))
    if analysis.title == DEFAULT_ANALYSIS_TITLE and not has_documents:
        analysis.title = title
    doc = Document(
        user_id=user.id,
        analysis_id=analysis.id,
        title=title,
        source_type=converted.source_type,
        source_url=source_url,
        mode="assistant",
        status="processing",
    )
    db.add(doc)
    await db.flush()
    try:
        doc.storage_path = await storage.save_pdf(doc.id, converted.pdf)
    except storage.StorageError as exc:
        raise AppError(str(exc), code="storage_error", status_code=502) from exc
    await db.commit()
    await db.refresh(doc)
    ingest.start_processing(doc.id, converted.extracted)
    return DocumentOut.model_validate(doc)


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia um arquivo (PDF, HTML ou TXT); a extração de regras continua em segundo plano",
    description=(
        "O arquivo é convertido na hora: um PDF sem texto (digitalizado), uma página sem "
        "conteúdo ou um formato desconhecido voltam com 422. HTML e TXT são diagramados em "
        "PDF, que é o que `GET /documents/{id}/file` devolve. Sem `analysis_id`, o "
        "documento ganha uma análise só dele."
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
async def get_document_file(document_id: uuid.UUID, user: UserDep, db: SessionDep) -> Response:
    doc = await _owned_document(db, document_id, user)
    try:
        data = await storage.read_pdf(doc.id)
    except storage.StorageError as exc:
        raise NotFoundError("Arquivo não encontrado.") from exc
    return Response(data, media_type="application/pdf")


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


@router.post(
    "/documents/{document_id}/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma regra a partir de um trecho selecionado na página",
    responses=error_responses(404, 409, 422),
)
async def create_rule(
    document_id: uuid.UUID, body: RuleCreateIn, user: UserDep, db: SessionDep
) -> RuleOut:
    doc = await _owned_document(db, document_id, user)
    if doc.status != "ready" or not doc.full_text:
        raise AppError(
            "Aguarde o documento terminar de ser lido.", code="not_ready", status_code=409
        )
    bounds = await page_range(db, document_id, body.page)
    span = bounds and find_excerpt(doc.full_text[: bounds[1]], body.excerpt, bounds[0])
    if not span:
        raise AppError(
            "Não encontrei esse trecho no texto da página. Tente selecionar de novo.",
            code="excerpt_not_found",
            status_code=422,
        )
    start, end = span
    rule = Rule(
        document_id=document_id,
        type=body.type,
        summary=body.summary,
        excerpt=doc.full_text[start:end],
        char_start=start,
        char_end=end,
        origin="manual",
    )
    db.add(rule)
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


@router.post(
    "/documents/{document_id}/queries",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Gera com a IA as buscas das regras nas bases da análise (em segundo plano)",
    description=(
        "Considera todas as regras não rejeitadas, inclusive as que a extração não ligou a "
        "nenhuma base (útil quando as bases chegaram depois do documento). O documento fica "
        "em `extracting_rules` até terminar."
    ),
    responses=error_responses(404, 409, 503),
)
async def generate_document_queries(
    document_id: uuid.UUID, body: GenerateQueriesIn, user: UserDep, db: SessionDep
) -> DocumentOut:
    doc = await _owned_document(db, document_id, user)
    if doc.status != "ready":
        raise ConflictError("Aguarde o documento terminar de ser analisado.", code="not_ready")
    if not await rule_queries.analysis_datasets(db, doc.analysis_id):
        raise ConflictError(
            "Envie ao menos uma base de dados (CSV) para gerar as buscas.", code="no_datasets"
        )
    try:
        llm.ensure_configured()
    except llm.LlmUnavailableError as exc:
        raise AppError(str(exc), code="llm_unavailable", status_code=503) from exc
    doc.status, doc.status_message = "extracting_rules", ingest.QUERIES_MESSAGE
    await db.commit()
    await db.refresh(doc)
    ingest.start_query_generation(document_id, overwrite=body.overwrite)
    return DocumentOut.model_validate(doc)


@router.put(
    "/rules/{rule_id}/query",
    summary="Define (ou corrige) a busca da regra e roda de novo",
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
    try:
        execution = await rule_queries.run_query(body, datasets)
    except QueryError as exc:
        raise AppError(str(exc), code="invalid_query", status_code=422) from exc
    rule_query = await _rule_query(db, rule.id)
    if rule_query is None:
        rule_query = RuleQuery(rule_id=rule.id, query={}, origin="manual", matched_rows=[])
        db.add(rule_query)
    rule_queries.set_query(rule_query, execution.normalized.model_dump(mode="json"), "manual")
    rule_queries.apply_execution(rule_query, execution)
    if execution.dataset.id not in (rule.dataset_ids or []):
        rule.dataset_ids = [*(rule.dataset_ids or []), execution.dataset.id]
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
    await rule_queries.execute(rule_query, await _rule_datasets(db, rule))
    await db.commit()
    return (await _rules_out(db, rule.document_id, [rule]))[0]


@router.delete(
    "/rules/{rule_id}/query",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a busca da regra",
    responses=error_responses(404),
)
async def delete_rule_query(rule_id: uuid.UUID, user: UserDep, db: SessionDep) -> Response:
    rule = await _owned_rule(db, rule_id, user)
    await db.execute(delete(RuleQuery).where(RuleQuery.rule_id == rule.id))
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
    if rule_query is None or rule_query.state != "ok" or rule_query.dataset_id is None:
        raise ConflictError("Esta regra não tem uma busca válida.", code="no_query")
    dataset = await db.get(Dataset, rule_query.dataset_id)
    if dataset is None:
        raise ConflictError("A base usada por esta busca foi removida.", code="no_query")
    try:
        if rule_query.match_count is not None and rule_query.match_count <= len(
            rule_query.matched_rows
        ):
            indices = list(rule_query.matched_rows)
        else:
            # Mais registros do que o guardado: roda a busca na hora.
            query = StructuredQuery.model_validate(rule_query.query)
            indices = (await rule_queries.run_query(query, [dataset])).rows
        loaded = await load_dataset(dataset.id, dataset.size_bytes, dataset.columns)
    except QueryError as exc:
        raise ConflictError(str(exc), code="no_query") from exc
    page = [i for i in indices[offset : offset + limit] if i < len(loaded.raw_rows)]
    return RecordsOut(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        columns=[c["name"] for c in dataset.columns],
        total=len(indices),
        offset=offset,
        rows=[RecordRow(index=i, values=loaded.raw_rows[i]) for i in page],
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
    try:
        return await rule_validation.records(
            rule,
            await _rule_datasets(db, rule),
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
