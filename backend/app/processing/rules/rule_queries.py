"""Buscas das regras nas bases: validação, prévia, execução e gravação.

A busca chega já aprovada pela pessoa (proposta pela IA a partir do trecho grifado ou
editada à mão). Nenhuma busca é gerada ou substituída automaticamente.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dataset, RuleQuery
from app.processing.ai import llm
from app.processing.datasets.duckdb_sql import query_sql
from app.processing.datasets.query_engine import (
    MAX_STORED_MATCHES,
    CompiledQuery,
    DatasetRef,
    QueryError,
    compile_query,
    fetch_rows,
    load_dataset,
    search,
)
from app.schemas.queries import RecordRow, RecordsOut, StructuredQuery

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


async def count_matches(
    query: StructuredQuery, datasets: list[Dataset]
) -> tuple[CompiledQuery, int]:
    """Prévia da busca na revisão: valida e conta os registros, sem gravar nada."""
    compiled = compile_query(query, dataset_refs(datasets))
    dataset = next(d for d in datasets if d.id == compiled.dataset.id)
    loaded = await load_dataset(dataset.id, dataset.size_bytes, dataset.columns)
    rows = await asyncio.to_thread(search, compiled, loaded.typed_rows, prefetch_limit=0)
    return compiled, len(rows)


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
