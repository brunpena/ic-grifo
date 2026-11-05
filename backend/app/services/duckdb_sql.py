"""Compila a linguagem restrita de regras para SQL parametrizado do DuckDB.

Colunas usam identificadores internos c0/c1, nunca nomes ou SQL enviados pelo modelo.
As mesmas validações de tipos/operadores do motor de regras são aplicadas antes daqui.
"""

import re
from datetime import date
from typing import Any

from app.schemas.queries import ConditionGroup, StructuredQuery
from app.schemas.validation import ComplianceCheck, DatasetCheck, Operand
from app.services.query_engine import DatasetRef, coerce
from app.services.text_normalization import fold


class SQLBuilder:
    def __init__(self, ref: DatasetRef) -> None:
        self.ref = ref
        self.params: dict[str, Any] = {}
        self.columns = {fold(c["name"]): (i, c) for i, c in enumerate(ref.columns)}
        self.exact_columns = {c["name"]: (i, c) for i, c in enumerate(ref.columns)}

    def parameter(self, value: Any) -> str:
        key = f"p{len(self.params)}"
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**63 - 1:
            # O binding Python pode converter inteiros enormes em DOUBLE; preserve o ID.
            self.params[key] = str(value)
            return f"CAST(${key} AS HUGEINT)"
        self.params[key] = value
        return f"${key}"

    def column(self, name: str) -> tuple[int, dict]:
        return self.exact_columns.get(name) or self.columns[fold(name)]

    def comparison(self, left: str, op: str, right: str | list[str] | None) -> str:
        if op in ("is_null", "not_null"):
            return f"({left} IS {'NOT ' if op == 'not_null' else ''}NULL)"
        if op in ("in", "not_in"):
            return f"({left} {'NOT IN' if op == 'not_in' else 'IN'} ({', '.join(right)}))"
        if op == "between":
            a, b = right
            return f"({left} BETWEEN least({a}, {b}) AND greatest({a}, {b}))"
        operators = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        if op in operators:
            return f"({left} {operators[op]} {right})"
        functions = {
            "contains": "contains",
            "not_contains": "contains",
            "starts_with": "starts_with",
            "ends_with": "ends_with",
        }
        expression = f"{functions[op]}({left}, {right})"
        return f"(NOT {expression})" if op == "not_contains" else expression

    def group(self, group: ConditionGroup, *, unknown_nulls: bool = False) -> str:
        parts = []
        for part in group.conditions:
            if isinstance(part, ConditionGroup):
                parts.append(self.group(part, unknown_nulls=unknown_nulls))
                continue
            index, column = self.column(part.column)
            left = f"{'f' if column['type'] == 'text' else 'c'}{index}"
            if part.op in ("is_null", "not_null"):
                expression = self.comparison(f"c{index}", part.op, None)
            else:
                raw = part.value if isinstance(part.value, list) else [part.value]
                values = [coerce(column, value) for value in raw]
                if column["type"] == "text":
                    values = [fold(str(value)) for value in values]
                parameters = [self.parameter(value) for value in values]
                right = parameters if isinstance(part.value, list) else parameters[0]
                expression = self.comparison(left, part.op, right)
            parts.append(expression if unknown_nulls else f"coalesce({expression}, false)")
        return "(" + f" {group.logic.upper()} ".join(parts) + ")" if parts else "TRUE"

    def operand(self, operand: Operand, today: date) -> tuple[str, str]:
        if operand.kind == "today":
            return "date", self.parameter(today)
        index, column = self.column(operand.column)
        cell, kind = f"c{index}", column["type"]
        if operand.kind == "column":
            return kind, f"f{index}" if kind == "text" else cell
        if operand.kind == "percentage":
            return "decimal", f"p{index}" if kind == "text" else cell
        if operand.kind == "deadline":
            unit = {"days": "DAY", "months": "MONTH", "years": "YEAR"}[operand.unit]
            quantity = self.parameter(operand.value)
            shifted = f"TRY({cell} + {quantity} * INTERVAL '1 {unit}')"
            return kind, f"(CASE WHEN year({shifted}) BETWEEN 1 AND 9999 THEN {shifted} END)"
        other_index, _ = self.column(operand.other_column)
        other = f"c{other_index}"
        if operand.kind == "days_between":
            difference = f"CAST({other} AS TIMESTAMP) - CAST({cell} AS TIMESTAMP)"
            return "decimal", f"(CASE WHEN {other} >= {cell} THEN epoch({difference}) / 86400 END)"
        # Converte antes da multiplicação para evitar overflow de inteiros na razão.
        return "decimal", f"(100.0 * CAST({cell} AS DOUBLE) / nullif({other}, 0))"

    def check(self, check: ComplianceCheck, today: date) -> str:
        kind, left = self.operand(check.left, today)
        if check.op in ("is_null", "not_null"):
            return self.comparison(left, check.op, None)
        if check.right.kind == "literal":
            value = check.right.value
            raw = value if isinstance(value, list) else [value]
            converted = [coerce({"type": kind}, v) for v in raw]
            if kind == "text":
                converted = [fold(str(v)) for v in converted]
            parameters = [self.parameter(v) for v in converted]
            right = parameters if isinstance(value, list) else parameters[0]
        else:
            _, right = self.operand(check.right, today)
        expression = self.comparison(left, check.op, right)
        guards = []
        if kind in ("integer", "decimal"):
            guards.append(f"NOT isfinite({left})")
            if not isinstance(right, list):
                guards.append(f"NOT isfinite({right})")
        if check.right.kind == "deadline":
            index, _ = self.column(check.right.column)
            guards.append(f"{left} < c{index}")
        if guards:
            expression = f"(CASE WHEN {' OR '.join(guards)} THEN NULL ELSE {expression} END)"
        return expression


def query_sql(query: StructuredQuery, ref: DatasetRef) -> tuple[str, dict]:
    builder = SQLBuilder(ref)
    where = builder.group(query)
    return f"SELECT _row_id FROM dados WHERE {where} ORDER BY _row_id", builder.params


def validation_sql(
    plan: DatasetCheck,
    ref: DatasetRef,
    today: date,
    *,
    uncertainty: bool,
    uncertain_scope: bool,
) -> tuple[str, dict]:
    builder = SQLBuilder(ref)
    scope = "NULL::BOOLEAN" if uncertain_scope else builder.group(plan.scope, unknown_nulls=True)
    checks = [builder.check(check, today) for check in plan.checks]
    passed = "(" + f" {plan.logic.upper()} ".join(checks) + ")"
    verdict = (
        "'inconclusiva'"
        if uncertainty
        else f"CASE WHEN scope IS NULL THEN 'inconclusiva' WHEN {passed} THEN 'conforme' "
        f"WHEN NOT {passed} THEN 'violacao' ELSE 'inconclusiva' END"
    )
    # Se há incerteza, os checks não são usados. Não enviar parâmetros sem referência.
    sql = (
        f"SELECT _row_id, CASE WHEN scope IS FALSE THEN NULL ELSE {verdict} END AS verdict "
        f"FROM (SELECT *, {scope} AS scope FROM dados)"
    )
    used_names = set(re.findall(r"\$(p\d+)\b", sql))
    used = {key: value for key, value in builder.params.items() if key in used_names}
    return sql, used


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _like(value: Any, prefix: str, suffix: str) -> str:
    return _literal(f"{prefix}{value}{suffix}")


def _readable_condition(column: str, op: str, value: Any) -> str:
    col = _identifier(column)
    if op in ("is_null", "not_null"):
        return f"{col} IS {'NOT ' if op == 'not_null' else ''}NULL"
    if op in ("in", "not_in"):
        values = value if isinstance(value, list) else [value]
        keyword = "NOT IN" if op == "not_in" else "IN"
        return f"{col} {keyword} ({', '.join(_literal(v) for v in values)})"
    if op == "between" and isinstance(value, list) and len(value) == 2:
        return f"{col} BETWEEN {_literal(value[0])} AND {_literal(value[1])}"
    operators = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if op in operators:
        return f"{col} {operators[op]} {_literal(value)}"
    patterns = {
        "contains": ("ILIKE", "%", "%"),
        "not_contains": ("NOT ILIKE", "%", "%"),
        "starts_with": ("ILIKE", "", "%"),
        "ends_with": ("ILIKE", "%", ""),
    }
    keyword, prefix, suffix = patterns[op]
    return f"{col} {keyword} {_like(value, prefix, suffix)}"


def _readable_group(group: ConditionGroup, depth: int) -> str:
    parts = [
        f"({_readable_group(part, depth + 1)})"
        if isinstance(part, ConditionGroup)
        else _readable_condition(part.column, part.op, part.value)
        for part in group.conditions
    ]
    if not parts:
        return "TRUE"
    separator = f"\n{'  ' * (depth + 1)}{group.logic.upper()} "
    return separator.join(parts)


def readable_sql(query: StructuredQuery, dataset_name: str | None = None) -> str:
    """SQL equivalente à busca, para a pessoa ler: nomes reais das colunas e valores no lugar
    dos parâmetros. Só é exibida; a execução usa sempre `query_sql`.

    Comparações de texto no motor ignoram maiúsculas e acentos (por isso ILIKE).
    """
    table = _identifier(dataset_name or query.dataset)
    lines = ["SELECT *", f"FROM {table}"]
    if query.conditions:
        lines.append(f"WHERE {_readable_group(query, 0)}")
    lines.append("ORDER BY linha;")
    return "\n".join(lines)
