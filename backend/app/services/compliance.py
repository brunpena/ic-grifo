"""Execução determinística de planos de conformidade, sem SQL ou código gerado.

Cada registro recebe conforme, violacao ou inconclusiva. Ausência de evidência nunca
vira conformidade. A interpretação da IA permanece visível separada da revisão humana.
"""

import calendar
import math
import operator
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.schemas.queries import ConditionGroup, StructuredQuery
from app.schemas.validation import (
    ComplianceCheck,
    DatasetCheck,
    DatasetValidation,
    Operand,
    RuleValidationOut,
    ValidationPlan,
    ValidationRecord,
)
from app.services.datasets import Value
from app.services.query_engine import (
    OPERATOR_LABELS,
    OPERATORS_BY_TYPE,
    DatasetRef,
    QueryError,
    coerce,
    compile_query,
    fold,
)

Outcome = bool | None
Row = list[Value]
COMPARISONS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def combine(values: list[Outcome], logic: str) -> Outcome:
    if logic == "and":
        return False if False in values else None if None in values else True
    return True if True in values else None if None in values else False


def _column(ref: DatasetRef, name: str | None) -> tuple[int, dict]:
    for i, column in enumerate(ref.columns):
        if name and fold(column["name"]) == fold(name):
            return i, column
    raise QueryError(f"A coluna “{name}” não existe na base “{ref.name}”.")


def _referenced(op: Operand) -> list[str]:
    names = []
    if op.kind in ("column", "percentage", "deadline", "days_between", "ratio_percent"):
        if not op.column:
            raise QueryError("O cálculo não informou a coluna.")
        names.append(op.column)
    if op.kind in ("days_between", "ratio_percent"):
        if not op.other_column:
            raise QueryError("O cálculo precisa de duas colunas.")
        names.append(op.other_column)
    return names


def _scope_columns(group: ConditionGroup) -> list[str]:
    return [
        name
        for part in group.conditions
        for name in (_scope_columns(part) if isinstance(part, ConditionGroup) else [part.column])
    ]


def _shift(start: date, quantity: int, unit: str) -> date:
    if unit == "days":
        return start + timedelta(days=quantity)
    months = quantity * (12 if unit == "years" else 1)
    year, month0 = divmod(start.year * 12 + start.month - 1 + months, 12)
    month = month0 + 1
    return start.replace(
        year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1])
    )


def _operand(op: Operand, ref: DatasetRef, today: date) -> tuple[str, Callable[[Row], Value]]:
    _referenced(op)
    if op.kind == "literal":
        raise QueryError("O lado esquerdo de uma verificação precisa vir dos dados.")
    if op.kind == "today":
        return "date", lambda _row: today
    index, column = _column(ref, op.column)
    kind = column["type"]
    if op.kind == "column":
        return kind, lambda row: row[index]
    if op.kind == "percentage":
        if kind not in ("text", "integer", "decimal"):
            raise QueryError("O percentual precisa de uma coluna de texto ou número.")

        def percent(row: Row) -> Value:
            cell = row[index]
            if cell is None:
                return None
            text = str(cell).strip()
            if kind == "text" and not text.endswith("%"):
                return None
            return coerce(
                {"type": "decimal", "format": column.get("format")}, text.removesuffix("%").strip()
            )

        return "decimal", percent
    if op.kind == "deadline":
        if kind not in ("date", "datetime"):
            raise QueryError("O início do prazo precisa ser uma data.")
        if (
            isinstance(op.value, bool)
            or not isinstance(op.value, int)
            or not 0 <= op.value <= 36500
        ):
            raise QueryError("A quantidade do prazo precisa ser um inteiro entre 0 e 36.500.")
        return (
            kind,
            lambda row: None if row[index] is None else _shift(row[index], op.value, op.unit),
        )
    other, other_column = _column(ref, op.other_column)
    if index == other:
        raise QueryError("O cálculo precisa de duas colunas diferentes.")
    if op.kind == "days_between":
        if kind not in ("date", "datetime") or other_column["type"] != kind:
            raise QueryError("A diferença de datas precisa de duas colunas do mesmo tipo de data.")

        def days(row: Row) -> Value:
            start, end = row[index], row[other]
            if start is None or end is None:
                return None
            if end < start:
                # Datas invertidas indicam ambiguidade/inconsistência, não prazo cumprido.
                return None
            return (end - start).total_seconds() / 86400

        return "decimal", days
    if kind not in ("integer", "decimal") or other_column["type"] not in ("integer", "decimal"):
        raise QueryError("O percentual calculado precisa de duas colunas numéricas.")
    return (
        "decimal",
        lambda row: (
            None
            if row[index] is None or row[other] in (None, 0)
            else (100 * row[index] / row[other])
        ),
    )


def _format(value: Value | list[Value]) -> str:
    if value is None:
        return "dado ausente ou inválido"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def compile_check(check: ComplianceCheck, ref: DatasetRef, today: date):
    if check.left == check.right:
        raise QueryError("Comparar uma coluna consigo mesma não verifica o cumprimento da regra.")
    kind, left = _operand(check.left, ref, today)
    if check.op not in OPERATORS_BY_TYPE[kind]:
        raise QueryError(f"O operador {check.op} não é compatível com {kind}.")
    if check.op in ("is_null", "not_null"):
        if check.left.kind != "column":
            raise QueryError("Verifique o preenchimento diretamente na coluna original.")
        if check.right is not None:
            raise QueryError("A verificação de preenchimento não recebe comparação.")
        return lambda row: ((left(row) is None) == (check.op == "is_null"), check.explanation)
    if check.right is None:
        raise QueryError("A verificação precisa do valor de comparação.")
    if check.right.kind == "literal":
        raw = check.right.value
        list_op = check.op in ("in", "not_in", "between")
        if list_op != isinstance(raw, list) or raw is None:
            raise QueryError("O valor de comparação está no formato errado.")
        items = raw if isinstance(raw, list) else [raw]
        if not items or len(items) > 200 or (check.op == "between" and len(items) != 2):
            raise QueryError("A lista de comparação tem tamanho inválido.")
        try:
            converted = [coerce({"type": kind}, v) for v in items]
        except ValueError as exc:
            raise QueryError("O valor não é compatível com o tipo da coluna.") from exc
        if kind in ("integer", "decimal") and any(not math.isfinite(v) for v in converted):
            raise QueryError("A comparação precisa de números finitos.")
        target = converted if list_op else converted[0]

        def right(_row):
            return target
    else:
        if check.op in ("in", "not_in", "between"):
            raise QueryError("Esse operador precisa de uma lista literal.")
        other_kind, right = _operand(check.right, ref, today)
        if kind != other_kind and {kind, other_kind} != {"integer", "decimal"}:
            raise QueryError("As colunas comparadas precisam de tipos compatíveis.")

    def evaluate(row: Row) -> tuple[Outcome, str]:
        try:
            a, b = left(row), right(row)
            if check.right.kind == "deadline" and a is not None:
                start_index, _ = _column(ref, check.right.column)
                start = row[start_index]
                if start is not None and a < start:
                    return None, f"{check.explanation}: a data final é anterior ao início do prazo."
            if a is None or b is None:
                return None, f"{check.explanation}: faltam valores para comparar."
            numbers = [v for v in (a, b) if isinstance(v, (int, float))]
            if any(not math.isfinite(v) for v in numbers):
                return None, f"{check.explanation}: número inválido na base."
            if kind == "text":
                a = fold(str(a))
                b = [fold(str(v)) for v in b] if isinstance(b, list) else fold(str(b))
            if check.op in COMPARISONS:
                result = COMPARISONS[check.op](a, b)
            elif check.op == "between":
                result = min(b) <= a <= max(b)
            elif check.op in ("in", "not_in"):
                result = (a in b) == (check.op == "in")
            elif check.op in ("contains", "not_contains"):
                result = (b in a) == (check.op == "contains")
            elif check.op == "starts_with":
                result = a.startswith(b)
            else:
                result = a.endswith(b)
            return (
                result,
                f"{check.explanation}: {_format(a)} {OPERATOR_LABELS[check.op]} {_format(b)}.",
            )
        except (ValueError, TypeError, OverflowError, ZeroDivisionError):
            return None, f"{check.explanation}: valor ausente, inválido ou cálculo impossível."

    return evaluate


def _scope(group: ConditionGroup, ref: DatasetRef):
    parts = []
    for item in group.conditions:
        if isinstance(item, ConditionGroup):
            parts.append(_scope(item, ref))
        else:
            index, _ = _column(ref, item.column)
            predicate = compile_query(
                StructuredQuery(dataset=ref.name, conditions=[item]), [ref]
            ).predicate

            def condition(row, index=index, item=item, predicate=predicate):
                if row[index] is None and item.op not in ("is_null", "not_null"):
                    return None
                return predicate(row)

            parts.append(condition)
    return lambda row: combine([p(row) for p in parts], group.logic) if parts else True


@dataclass
class CompiledValidation:
    scope: Callable[[Row], Outcome]
    checks: list
    logic: str
    uncertainty: list[str]

    def evaluate(self, row: Row) -> tuple[str | None, str]:
        applies = self.scope(row)
        if applies is False:
            return None, "Fora do escopo da regra."
        if self.uncertainty:
            return "inconclusiva", "; ".join(self.uncertainty)
        if applies is None:
            return "inconclusiva", "Faltam dados para determinar se a regra se aplica."
        checked = [check(row) for check in self.checks]
        result = combine([outcome for outcome, _ in checked], self.logic)
        verdict = (
            "conforme" if result is True else "violacao" if result is False else "inconclusiva"
        )
        return verdict, " ".join(detail for _, detail in checked)


def compile_validation(
    plan: DatasetCheck, ref: DatasetRef, today: date, missing_data: list[str]
) -> CompiledValidation:
    normalized = compile_query(plan.scope, [ref]).normalized
    names = _scope_columns(normalized)
    if any(not (_referenced(c.left) or (c.right and _referenced(c.right))) for c in plan.checks):
        raise QueryError("Cada critério precisa verificar ao menos uma coluna da base.")
    for check in plan.checks:
        names.extend(_referenced(check.left))
        if check.right:
            names.extend(_referenced(check.right))
    uncertainty = list(missing_data)
    for name in dict.fromkeys(names):
        _, col = _column(ref, name)
        meaning = col.get("semantic") or {}
        if meaning.get("confidence") != "high":
            uncertainty.append(
                f"Significado da coluna “{col['name']}” não confirmado: "
                f"{meaning.get('reason') or 'sem interpretação da IA'}"
            )
    # Sem certeza do escopo, nenhuma linha pode ser descartada como não aplicável.
    uncertain_scope = any(
        ((_column(ref, n)[1].get("semantic") or {}).get("confidence")) != "high"
        for n in _scope_columns(normalized)
    )
    return CompiledValidation(
        scope=(lambda _row: None) if uncertain_scope else _scope(normalized, ref),
        checks=[compile_check(c, ref, today) for c in plan.checks],
        logic=plan.logic,
        uncertainty=uncertainty,
    )


def evaluate_rows(
    compiled: CompiledValidation,
    raw_rows: list[list[str | None]],
    rows: list[Row],
    *,
    offset: int = 0,
    limit: int = 100,
    verdict: str | None = None,
) -> tuple[dict[str, int], int, list[ValidationRecord]]:
    counts = {"applicable_count": 0, "passed_count": 0, "failed_count": 0, "unknown_count": 0}
    page: list[ValidationRecord] = []
    total = 0
    for index, row in enumerate(rows):
        result, explanation = compiled.evaluate(row)
        if result is None:
            continue
        counts["applicable_count"] += 1
        key = {
            "conforme": "passed_count",
            "violacao": "failed_count",
            "inconclusiva": "unknown_count",
        }[result]
        counts[key] += 1
        if verdict is not None and result != verdict:
            continue
        if offset <= total < offset + limit:
            page.append(
                ValidationRecord(
                    index=index, values=raw_rows[index], verdict=result, explanation=explanation
                )
            )
        total += 1
    return counts, total, page


def summarize(
    plan: ValidationPlan, datasets: list[DatasetValidation], checked_at: datetime, errors: list[str]
) -> RuleValidationOut:
    counts = {
        key: sum(getattr(d, key) for d in datasets)
        for key in ("applicable_count", "passed_count", "failed_count", "unknown_count")
    }
    missing = list(dict.fromkeys([*plan.missing_data, *errors]))
    if counts["failed_count"]:
        status = "violacao"
    elif missing or counts["unknown_count"] or not datasets:
        status = "inconclusiva"
    elif not counts["applicable_count"]:
        status = "nao_aplicavel"
    else:
        status = "conforme"
    return RuleValidationOut(
        status=status,
        explanation=plan.explanation,
        checked_at=checked_at,
        missing_data=missing,
        datasets=datasets,
        **counts,
    )
