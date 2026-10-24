"""Validação e execução das buscas estruturadas sobre as bases em CSV.

Somente leitura por construção: não há SQL nem `eval`. A busca é conferida contra o
schema da base (coluna existe, operador serve para o tipo, valor converte para o tipo)
e vira uma função Python que filtra as linhas já tipadas.

Comparações de texto ignoram maiúsculas, acentos e espaços repetidos. Células vazias só
entram em `is_null`: qualquer outra comparação com elas é falsa (como no SQL).
"""

import asyncio
import re
import unicodedata
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.schemas.queries import (
    MAX_CONDITIONS,
    MAX_DEPTH,
    Condition,
    ConditionGroup,
    Scalar,
    StructuredQuery,
)
from app.services import storage
from app.services.datasets import FALSE_VALUES, TRUE_VALUES, Value, parse_csv, parse_value

_CANONICAL_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")
MAX_LIST_VALUES = 200
MAX_STORED_MATCHES = 50_000
CACHE_SIZE = 4

ORDERED = {"eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "is_null", "not_null"}
OPERATORS_BY_TYPE: dict[str, set[str]] = {
    "integer": ORDERED,
    "decimal": ORDERED,
    "date": ORDERED,
    "datetime": ORDERED,
    "boolean": {"eq", "ne", "is_null", "not_null"},
    "text": {
        "eq", "ne", "in", "not_in", "contains", "not_contains", "starts_with", "ends_with",
        "is_null", "not_null",
    },
}  # fmt: skip
OPERATOR_LABELS = {
    "eq": "igual a", "ne": "diferente de", "gt": "maior que", "gte": "maior ou igual a",
    "lt": "menor que", "lte": "menor ou igual a", "between": "entre", "in": "um de",
    "not_in": "nenhum de", "contains": "contém", "not_contains": "não contém",
    "starts_with": "começa com", "ends_with": "termina com", "is_null": "vazio",
    "not_null": "preenchido",
}  # fmt: skip
TYPE_LABELS = {
    "integer": "número inteiro", "decimal": "número", "date": "data", "datetime": "data e hora",
    "boolean": "sim/não", "text": "texto",
}  # fmt: skip

Row = Sequence[Value]
Predicate = Callable[[Row], bool]


class QueryError(Exception):
    """Busca inválida para a base. A mensagem, em português, vai para a pessoa."""


@dataclass(frozen=True)
class DatasetRef:
    id: uuid.UUID
    name: str
    columns: list[dict]


@dataclass
class CompiledQuery:
    dataset: DatasetRef
    # A busca com os nomes de coluna exatos e os valores já no tipo da coluna.
    normalized: StructuredQuery
    predicate: Predicate


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def _as_number(column: dict, value: Scalar) -> float:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    # Número canônico (como no JSON) primeiro: "1234.5" não pode virar 12345 numa coluna "br".
    if _CANONICAL_NUMBER.fullmatch(text):
        return float(text)
    for fmt in (column.get("format"), "br", "us"):
        parsed = parse_value({"type": "decimal", "format": fmt}, text)
        if isinstance(parsed, float):
            return parsed
    raise ValueError


def _as_date(value: Scalar) -> date:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError


def _as_datetime(value: Scalar) -> datetime:
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    day = _as_date(text)
    return datetime(day.year, day.month, day.day)


def _as_bool(value: Scalar) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError


def coerce(column: dict, value: Scalar) -> Value:
    """Valor da busca no tipo da coluna; ValueError se não converter."""
    kind = column["type"]
    if kind in ("integer", "decimal"):
        number = _as_number(column, value)
        return int(number) if kind == "integer" and number.is_integer() else number
    if kind == "date":
        return _as_date(value)
    if kind == "datetime":
        return _as_datetime(value)
    if kind == "boolean":
        return _as_bool(value)
    return str(value)


def _json_value(value: Value) -> Scalar:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    assert value is not None
    return value


class _Compiler:
    def __init__(self, dataset: DatasetRef) -> None:
        self.dataset = dataset
        self.by_name = {c["name"]: i for i, c in enumerate(dataset.columns)}
        self.by_folded = {fold(c["name"]): i for i, c in enumerate(dataset.columns)}
        self.count = 0

    def column(self, name: str) -> tuple[int, dict]:
        index = self.by_name.get(name)
        if index is None:
            index = self.by_folded.get(fold(name))
        if index is None:
            raise QueryError(f"A coluna “{name}” não existe na base “{self.dataset.name}”.")
        return index, self.dataset.columns[index]

    def group(self, group: ConditionGroup, depth: int) -> tuple[ConditionGroup, Predicate]:
        if depth > MAX_DEPTH:
            raise QueryError(f"A busca pode ter no máximo {MAX_DEPTH} níveis de grupos.")
        parts: list[Condition | ConditionGroup] = []
        predicates: list[Predicate] = []
        for item in group.conditions:
            if isinstance(item, ConditionGroup):
                normalized, predicate = self.group(item, depth + 1)
            else:
                normalized, predicate = self.condition(item)
            parts.append(normalized)
            predicates.append(predicate)
        combine = all if group.logic == "and" else any
        if not predicates:
            return ConditionGroup(logic=group.logic, conditions=[]), lambda _row: True
        return ConditionGroup(logic=group.logic, conditions=parts), lambda row: combine(
            p(row) for p in predicates
        )

    def condition(self, condition: Condition) -> tuple[Condition, Predicate]:
        self.count += 1
        if self.count > MAX_CONDITIONS:
            raise QueryError(f"A busca pode ter no máximo {MAX_CONDITIONS} condições.")
        index, column = self.column(condition.column)
        name, kind, op = column["name"], column["type"], condition.op
        if op not in OPERATORS_BY_TYPE[kind]:
            raise QueryError(
                f"O operador “{OPERATOR_LABELS[op]}” não serve para a coluna “{name}”, "
                f"que é do tipo {TYPE_LABELS[kind]}."
            )
        if op in ("is_null", "not_null"):
            wants_null = op == "is_null"
            return Condition(column=name, op=op), lambda row: (row[index] is None) == wants_null

        raw = condition.value
        expects_list = op in ("between", "in", "not_in")
        if expects_list:
            if not isinstance(raw, list) or not raw:
                raise QueryError(
                    f"“{OPERATOR_LABELS[op]}” precisa de uma lista de valores ({name})."
                )
            if op == "between" and len(raw) != 2:
                raise QueryError(f"“entre” precisa de exatamente dois valores ({name}).")
            if len(raw) > MAX_LIST_VALUES:
                raise QueryError(f"Use no máximo {MAX_LIST_VALUES} valores na lista ({name}).")
            items = raw
        else:
            if raw is None or isinstance(raw, list) or (isinstance(raw, str) and not raw.strip()):
                raise QueryError(f"Informe um valor para a condição na coluna “{name}”.")
            items = [raw]
        try:
            values = [coerce(column, item) for item in items]
        except ValueError as exc:
            bad = ", ".join(str(i) for i in items)
            raise QueryError(
                f"“{bad}” não é um valor válido de {TYPE_LABELS[kind]} para a coluna “{name}”."
            ) from exc
        if op == "between" and values[0] > values[1]:
            values.reverse()

        stored: Scalar | list[Scalar] = (
            [_json_value(v) for v in values] if expects_list else _json_value(values[0])
        )
        normalized = Condition(column=name, op=op, value=stored)
        if kind == "text":
            return normalized, _text_predicate(index, op, [fold(str(v)) for v in values])
        return normalized, _ordered_predicate(index, op, values)


def _ordered_predicate(index: int, op: str, values: list[Value]) -> Predicate:
    first = values[0]
    tests: dict[str, Callable[[Value], bool]] = {
        "eq": lambda v: v == first,
        "ne": lambda v: v != first,
        "gt": lambda v: v > first,
        "gte": lambda v: v >= first,
        "lt": lambda v: v < first,
        "lte": lambda v: v <= first,
        "between": lambda v: first <= v <= values[1],
        "in": lambda v: v in values,
        "not_in": lambda v: v not in values,
    }
    test = tests[op]

    def predicate(row: Row) -> bool:
        cell = row[index]
        return cell is not None and test(cell)

    return predicate


def _text_predicate(index: int, op: str, values: list[str]) -> Predicate:
    first = values[0]
    tests: dict[str, Callable[[str], bool]] = {
        "eq": lambda v: v == first,
        "ne": lambda v: v != first,
        "in": lambda v: v in values,
        "not_in": lambda v: v not in values,
        "contains": lambda v: first in v,
        "not_contains": lambda v: first not in v,
        "starts_with": lambda v: v.startswith(first),
        "ends_with": lambda v: v.endswith(first),
    }
    test = tests[op]

    def predicate(row: Row) -> bool:
        cell = row[index]
        return cell is not None and test(fold(str(cell)))

    return predicate


def compile_query(query: StructuredQuery, datasets: Sequence[DatasetRef]) -> CompiledQuery:
    by_name = {d.name: d for d in datasets}
    dataset = by_name.get(query.dataset) or next(
        (d for d in datasets if fold(d.name) == fold(query.dataset)), None
    )
    if dataset is None:
        names = ", ".join(f"“{d.name}”" for d in datasets) or "nenhuma"
        raise QueryError(f"A base “{query.dataset}” não existe nesta análise (bases: {names}).")
    compiler = _Compiler(dataset)
    group, predicate = compiler.group(query, 1)
    normalized = StructuredQuery(
        dataset=dataset.name, logic=group.logic, conditions=group.conditions
    )
    return CompiledQuery(dataset=dataset, normalized=normalized, predicate=predicate)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


@dataclass
class LoadedDataset:
    raw_rows: list[list[str | None]]
    typed_rows: list[list[Value]]


_cache: OrderedDict[tuple[uuid.UUID, int], LoadedDataset] = OrderedDict()
_cache_lock = asyncio.Lock()


def _load(data: bytes, columns: list[dict]) -> LoadedDataset:
    parsed = parse_csv(data, max_rows=10**9, max_columns=10**6)
    typed = [[parse_value(c, row[i]) for i, c in enumerate(columns)] for row in parsed.rows]
    return LoadedDataset(raw_rows=parsed.rows, typed_rows=typed)


async def load_dataset(
    dataset_id: uuid.UUID, size_bytes: int, columns: list[dict]
) -> LoadedDataset:
    """Linhas da base (texto e tipadas), com cache das últimas bases usadas."""
    key = (dataset_id, size_bytes)
    async with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        try:
            data = await storage.read_file(storage.dataset_name(dataset_id))
        except storage.StorageError as exc:
            raise QueryError("O arquivo da base não foi encontrado. Envie a base de novo.") from exc
        loaded = await asyncio.to_thread(_load, data, columns)
        _cache[key] = loaded
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return loaded


def run(compiled: CompiledQuery, rows: list[list[Value]]) -> list[int]:
    predicate = compiled.predicate
    return [i for i, row in enumerate(rows) if predicate(row)]
