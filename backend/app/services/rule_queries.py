"""Buscas das regras nas bases: geração pela IA, validação, execução e gravação.

A busca gerada pela IA que não passa na validação é guardada mesmo assim, com
`state = "erro"` e a mensagem, para a pessoa poder corrigir na tela. Buscas editadas à
mão (`origin = "manual"`) nunca são substituídas pela IA.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dataset, Document, Rule, RuleQuery
from app.schemas.queries import RecordRow, RecordsOut, StructuredQuery
from app.services import llm
from app.services.duckdb_sql import query_sql
from app.services.query_engine import (
    MAX_STORED_MATCHES,
    CompiledQuery,
    DatasetRef,
    QueryError,
    compile_query,
    fetch_rows,
    load_dataset,
    search,
)

logger = logging.getLogger(__name__)


async def analysis_datasets(
    db: AsyncSession, analysis_id: uuid.UUID, *, include_processing: bool = False
) -> list[Dataset]:
    """Bases prontas da análise; as que ainda estão sendo lidas (ou falharam) ficam de fora."""
    datasets = list(
        (
            await db.scalars(
                select(Dataset)
                .where(
                    Dataset.analysis_id == analysis_id,
                    Dataset.status.in_(
                        ("ready", "processing") if include_processing else ("ready",)
                    ),
                )
                .order_by(Dataset.created_at)
            )
        ).all()
    )
    return [d for d in datasets if d.columns]


def dataset_refs(datasets: list[Dataset]) -> list[DatasetRef]:
    return [DatasetRef(id=d.id, name=d.name, columns=d.columns) for d in datasets]


def dataset_prompts(datasets: list[Dataset]) -> list[llm.DatasetPrompt]:
    return [
        llm.DatasetPrompt(name=d.name, row_count=d.row_count, columns=d.columns) for d in datasets
    ]


@dataclass
class Execution:
    dataset: Dataset
    # A busca com nomes de coluna exatos e valores no tipo da coluna (é o que se grava).
    normalized: StructuredQuery
    rows: Sequence[int]


async def run_query(query: StructuredQuery, datasets: list[Dataset]) -> Execution:
    """Valida e roda a busca. Lança QueryError com a mensagem para a pessoa."""
    compiled = compile_query(query, dataset_refs(datasets))
    dataset = next(d for d in datasets if d.id == compiled.dataset.id)
    loaded = await load_dataset(dataset.id, dataset.size_bytes, dataset.columns)
    rows = await asyncio.to_thread(search, compiled, loaded.typed_rows)
    return Execution(dataset=dataset, normalized=compiled.normalized, rows=rows)


def apply_execution(rule_query: RuleQuery, execution: Execution) -> None:
    rule_query.executed_at = datetime.now(UTC)
    rule_query.query = execution.normalized.model_dump(mode="json")
    rule_query.dataset_id = execution.dataset.id
    rule_query.state = "ok"
    rule_query.error = None
    rule_query.match_count = len(execution.rows)
    rule_query.matched_rows = execution.rows[:MAX_STORED_MATCHES]


def mark_failed(rule_query: RuleQuery, message: str) -> None:
    rule_query.executed_at = datetime.now(UTC)
    rule_query.state = "erro"
    rule_query.error = message
    rule_query.match_count = None
    rule_query.matched_rows = []


async def execute(rule_query: RuleQuery, datasets: list[Dataset]) -> None:
    """Roda a busca e grava o resultado na linha (sem commit)."""
    try:
        prepare_query(rule_query, datasets)
        execution = await run_query(StructuredQuery.model_validate(rule_query.query), datasets)
    except QueryError as exc:
        mark_failed(rule_query, str(exc))
    except ValidationError:
        mark_failed(rule_query, "A busca está num formato inválido.")
    else:
        apply_execution(rule_query, execution)


def set_query(rule_query: RuleQuery, query: dict, origin: str) -> None:
    """Troca a busca. A verificação anterior (segue/viola) deixa de valer."""
    rule_query.query = query
    rule_query.origin = origin
    rule_query.state = "pendente"
    rule_query.sql = None
    rule_query.sql_parameters = None
    rule_query.error = None
    rule_query.match_count = None
    rule_query.matched_rows = []
    rule_query.executed_at = None
    rule_query.verdict = None
    rule_query.verdict_details = None


def prepare_query(rule_query: RuleQuery, datasets: list[Dataset]) -> CompiledQuery:
    """Valida e salva a SQL, sem abrir o DuckDB ou executar a consulta.

    Na execução recompilamos os critérios validados contra o schema atual; SQL livre
    do cliente/modelo ou uma string persistida adulterada nunca é executada.
    """
    compiled = compile_query(
        StructuredQuery.model_validate(rule_query.query), dataset_refs(datasets)
    )
    sql, parameters = query_sql(compiled.normalized, compiled.dataset)
    rule_query.query = compiled.normalized.model_dump(mode="json")
    rule_query.dataset_id = compiled.dataset.id
    rule_query.sql = sql
    rule_query.sql_parameters = json.loads(json.dumps(parameters, default=str))
    return compiled


async def execute_page(
    rule_query: RuleQuery, datasets: list[Dataset], *, offset: int, limit: int
) -> RecordsOut:
    """Selecionar uma regra executa a SQL local e traz somente a página solicitada."""
    compiled = prepare_query(rule_query, datasets)
    dataset = next(d for d in datasets if d.id == compiled.dataset.id)
    loaded = await load_dataset(dataset.id, dataset.size_bytes, dataset.columns)

    def page():
        indices = search(compiled, loaded.typed_rows, prefetch_limit=0)
        selected = indices[offset : offset + limit]
        values = fetch_rows(loaded.raw_rows, selected)
        return len(indices), [RecordRow(index=i, values=values[i]) for i in selected]

    total, rows = await asyncio.to_thread(page)
    rule_query.state, rule_query.error = "ok", None
    rule_query.match_count, rule_query.matched_rows = total, []
    rule_query.executed_at = datetime.now(UTC)
    return RecordsOut(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        columns=[c["name"] for c in dataset.columns],
        total=total,
        offset=offset,
        rows=rows,
    )


@dataclass
class GenerationResult:
    generated: int = 0
    # Regras para as quais a IA disse que nenhuma base serve.
    without_dataset: int = 0
    failed: int = 0


async def generate_for_document(
    db: AsyncSession, document_id: uuid.UUID, *, overwrite: bool, only_related: bool
) -> GenerationResult:
    """Gera e prepara as consultas SQL sem executar buscas nos registros.

    `only_related`: só as regras que a extração ligou a alguma base.
    `overwrite`: refaz também as buscas que a IA já tinha gerado (nunca as manuais).
    """
    result = GenerationResult()
    document = await db.get(Document, document_id)
    if document is None:
        return result
    datasets = await analysis_datasets(db, document.analysis_id)
    if not datasets:
        return result
    # A geração usa os significados já interpretados; só interpreta os que faltam.
    from app.services.rule_validation import ensure_meanings

    await ensure_meanings(db, datasets, refresh=False)
    rules = (
        await db.scalars(
            select(Rule)
            .where(Rule.document_id == document_id, Rule.status != "rejeitada")
            .order_by(Rule.char_start)
        )
    ).all()
    existing = {
        q.rule_id: q
        for q in await db.scalars(
            select(RuleQuery).where(RuleQuery.rule_id.in_([r.id for r in rules]))
        )
    }
    pending = [
        r
        for r in rules
        if (not only_related or r.dataset_ids)
        and (r.id not in existing or (overwrite and existing[r.id].origin == "ia"))
    ]
    if not pending:
        return result

    prompts = [
        llm.RulePrompt(ref=i + 1, type=r.type, summary=r.summary, excerpt=r.excerpt)
        for i, r in enumerate(pending)
    ]
    # Objetos permanecem disponíveis (expire_on_commit=False), mas a conexão é liberada.
    await db.commit()
    generated = await llm.generate_queries(prompts, dataset_prompts(datasets))

    remove_ids: list[uuid.UUID] = []
    for prompt, rule in zip(prompts, pending, strict=True):
        answer = generated.get(prompt.ref)
        if answer is None:
            continue
        current = existing.get(rule.id)
        if answer.dataset is None:
            result.without_dataset += 1
            if current is not None:
                remove_ids.append(current.id)
            continue
        if current is None:
            current = RuleQuery(rule_id=rule.id, query={}, origin="ia", matched_rows=[])
            db.add(current)
        set_query(current, answer.query, "ia")
        try:
            prepare_query(current, datasets)
        except (QueryError, ValidationError) as exc:
            mark_failed(current, str(exc))
            current.executed_at = None
        if current.state == "pendente":
            result.generated += 1
        else:
            result.failed += 1
            logger.info(
                "rule_query_invalid", extra={"rule_id": str(rule.id), "error": current.error}
            )
    if remove_ids:
        await db.execute(delete(RuleQuery).where(RuleQuery.id.in_(remove_ids)))
    await db.commit()
    return result
