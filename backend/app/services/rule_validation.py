"""Interpretação das bases, cobertura de todas as regras e resultados persistidos."""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dataset, Document, Rule
from app.schemas.validation import (
    DatasetValidation,
    RuleValidationOut,
    ValidationPlan,
    ValidationRecordsOut,
)
from app.services import compliance, llm, rule_queries, validation_llm
from app.services.query_engine import DatasetRef, QueryError, fold, load_dataset

logger = logging.getLogger(__name__)


def result(status: str, explanation: str, missing: list[str] | None = None) -> dict:
    return RuleValidationOut(
        status=status,
        explanation=explanation,
        checked_at=datetime.now(UTC),
        missing_data=missing or [],
    ).model_dump(mode="json")


async def interpret(name: str, columns: list[dict]) -> tuple[list[dict], str | None]:
    try:
        interpreted = await validation_llm.interpret_columns(name, columns)
    except (llm.LlmApiError, llm.LlmUnavailableError) as exc:
        message = str(exc)
        return [
            {**c, "semantic": validation_llm.uncertain_column(message)} for c in columns
        ], message
    return interpreted, None


async def ensure_meanings(db: AsyncSession, datasets: list[Dataset], *, refresh: bool) -> None:
    changed = False
    for dataset in datasets:
        if refresh or any(not c.get("semantic") for c in dataset.columns):
            dataset.columns, warning = await interpret(dataset.name, dataset.columns)
            dataset.status_message = warning
            changed = True
    if changed and datasets:
        await invalidate_analysis(db, datasets[0].analysis_id)
    await db.commit()


async def invalidate_analysis(db: AsyncSession, analysis_id: uuid.UUID) -> None:
    documents = select(Document.id).where(Document.analysis_id == analysis_id)
    await db.execute(
        update(Rule)
        .where(Rule.document_id.in_(documents), Rule.status != "rejeitada")
        .values(validation=None)
    )


def source_signature(dataset) -> str:
    payload = (dataset.status, dataset.size_bytes, dataset.original_size_bytes, dataset.columns)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def _sources(db: AsyncSession, analysis_id: uuid.UUID) -> dict[str, str]:
    return {
        str(row.id): source_signature(row)
        for row in await db.execute(
            select(
                Dataset.id,
                Dataset.status,
                Dataset.size_bytes,
                Dataset.original_size_bytes,
                Dataset.columns,
            ).where(Dataset.analysis_id == analysis_id)
        )
    }


def measured_business_days(plan: ValidationPlan, datasets: list[Dataset]) -> bool:
    """Uma duração já expressa em dias úteis dispensa recalcular feriados."""
    by_name = {d.name: d for d in datasets}
    if not plan.datasets:
        return False
    for part in plan.datasets:
        dataset = by_name.get(part.scope.dataset)
        if dataset is None:
            return False
        measured = False
        for check in part.checks:
            for operand in (check.left, check.right):
                if operand is None:
                    continue
                if operand.kind in ("days_between", "deadline"):
                    return False
                if operand.kind != "column":
                    continue
                column = next((c for c in dataset.columns if c["name"] == operand.column), {})
                semantic = column.get("semantic") or {}
                if (
                    column.get("type") in ("integer", "decimal")
                    and semantic.get("confidence") == "high"
                    and fold(semantic.get("unit") or "")
                    in ("dia util", "dias uteis", "business_days")
                ):
                    measured = True
        if not measured:
            return False
    return True


async def evaluate_plan(
    plan: ValidationPlan, datasets: list[Dataset], checked_at: datetime
) -> RuleValidationOut:
    refs = {d.name: d for d in datasets}
    checked: list[DatasetValidation] = []
    errors: list[str] = [
        f"A base “{d.name}” foi cortada pelo limite de armazenamento. "
        "O resultado cobre somente as linhas guardadas."
        for d in datasets
        if d.original_size_bytes and d.original_size_bytes > d.size_bytes
    ]
    used: set[uuid.UUID] = set()
    for check in plan.datasets:
        dataset = refs.get(check.scope.dataset)
        if dataset is None:
            errors.append(f"A base “{check.scope.dataset}” não está disponível nesta análise.")
            continue
        if dataset.id in used:
            errors.append(f"A IA repetiu a base “{dataset.name}” no plano.")
            continue
        used.add(dataset.id)
        try:
            compiled = compliance.compile_validation(
                check,
                DatasetRef(id=dataset.id, name=dataset.name, columns=dataset.columns),
                checked_at.date(),
                plan.missing_data,
            )
            loaded = await load_dataset(dataset.id, dataset.size_bytes, dataset.columns)
            counts, _, _ = await asyncio.to_thread(
                compliance.evaluate_rows, compiled, loaded.raw_rows, loaded.typed_rows, limit=0
            )
            checked.append(
                DatasetValidation(
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    explanation="; ".join(compiled.uncertainty),
                    **counts,
                )
            )
            errors.extend(compiled.uncertainty)
        except (QueryError, ValueError) as exc:
            errors.append(str(exc))
    return compliance.summarize(plan, checked, checked_at, errors)


async def validate_document(
    db: AsyncSession, document_id: uuid.UUID, *, refresh_columns: bool = False
) -> None:
    document = await db.get(Document, document_id)
    if document is None:
        return
    rules = list(
        await db.scalars(
            select(Rule).where(Rule.document_id == document_id).order_by(Rule.char_start)
        )
    )
    datasets = await rule_queries.analysis_datasets(db, document.analysis_id)
    await ensure_meanings(db, datasets, refresh=refresh_columns)
    sources = await _sources(db, document.analysis_id)
    active = [r for r in rules if r.status != "rejeitada"]
    for rule in rules:
        rule.validation = (
            result("ignorada", "Regra rejeitada na revisão humana.")
            if (rule.status == "rejeitada")
            else None
        )
    await db.commit()
    if not datasets:
        for rule in active:
            rule.validation = result(
                "inconclusiva",
                "Não há bases de dados prontas para verificar a regra.",
                ["Envie uma base CSV com os dados exigidos pela regra."],
            )
        await db.commit()
        return
    checked_at = datetime.now(UTC)
    prompts = [
        llm.RulePrompt(ref=i + 1, type=r.type, summary=r.summary, excerpt=r.excerpt)
        for i, r in enumerate(active)
    ]
    try:
        plans = await validation_llm.plan_rules(
            prompts, rule_queries.dataset_prompts(datasets), checked_at.date().isoformat()
        )
    except (llm.LlmApiError, llm.LlmUnavailableError) as exc:
        plans = {}
        failure = str(exc)
    else:
        failure = "A IA não devolveu um plano válido para esta regra. Tente validar novamente."
    for prompt, rule in zip(prompts, active, strict=True):
        plan = plans.get(prompt.ref)
        if plan is None:
            rule.validation = result("erro", failure)
            continue
        # Sem calendário/localidade, dias úteis não podem virar dias corridos por
        # engano do modelo. O plano permanece visível, com evidência insuficiente.
        if any(
            term in fold(rule.excerpt) for term in ("dias uteis", "dia util")
        ) and not measured_business_days(plan, datasets):
            plan = plan.model_copy(
                update={
                    "missing_data": [
                        *plan.missing_data,
                        "Prazo em dias úteis exige calendário de feriados e localidade, "
                        "ainda não disponíveis.",
                    ]
                }
            )
        try:
            outcome = await evaluate_plan(plan, datasets, checked_at)
            rule.validation = {
                **outcome.model_dump(mode="json"),
                "_plan": plan.model_dump(mode="json"),
                "_sources": sources,
            }
        except Exception:
            logger.exception("rule_validation_failed", extra={"rule_id": str(rule.id)})
            rule.validation = result(
                "erro", "Não foi possível verificar esta regra. Tente novamente."
            )
    # Bases em processamento, adicionadas ou removidas durante a avaliação impedem uma
    # conclusão geral definitiva. Nunca reaproveita uma aprovação com fontes incompletas.
    if sources != await _sources(db, document.analysis_id) or set(sources) != {
        str(d.id) for d in datasets
    }:
        for rule in active:
            rule.validation = {
                **(rule.validation or {}),
                "status": "desatualizada",
                "explanation": "As bases mudaram ou ainda estão sendo lidas. Valide novamente.",
            }
    await db.commit()


async def records(
    rule: Rule,
    datasets: list[Dataset],
    dataset_id: uuid.UUID,
    *,
    offset: int,
    limit: int,
    verdict: str | None,
) -> ValidationRecordsOut:
    saved = rule.validation or {}
    if saved.get("status") in ("desatualizada", "ignorada") or not saved.get("_plan"):
        raise QueryError("Esta regra precisa ser validada novamente.")
    if saved.get("_sources") != {str(d.id): source_signature(d) for d in datasets}:
        raise QueryError("As bases ou suas colunas mudaram. Valide a regra novamente.")
    plan = ValidationPlan.model_validate(saved["_plan"])
    dataset = next((d for d in datasets if d.id == dataset_id), None)
    if dataset is None:
        raise QueryError("A base não está disponível nesta análise.")
    check = next((p for p in plan.datasets if p.scope.dataset == dataset.name), None)
    if check is None:
        raise QueryError("Esta base não participa da verificação da regra.")
    checked_at = datetime.fromisoformat(saved["checked_at"])
    compiled = compliance.compile_validation(
        check,
        DatasetRef(id=dataset.id, name=dataset.name, columns=dataset.columns),
        checked_at.date(),
        plan.missing_data,
    )
    loaded = await load_dataset(dataset.id, dataset.size_bytes, dataset.columns)
    _, total, page = await asyncio.to_thread(
        compliance.evaluate_rows,
        compiled,
        loaded.raw_rows,
        loaded.typed_rows,
        offset=offset,
        limit=limit,
        verdict=verdict,
    )
    return ValidationRecordsOut(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        columns=[c["name"] for c in dataset.columns],
        total=total,
        offset=offset,
        rows=page,
    )
