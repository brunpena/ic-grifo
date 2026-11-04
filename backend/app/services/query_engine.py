"""Validação das buscas e execução SQL no cache DuckDB persistente.

A busca é conferida contra o schema e compilada para SQL parametrizado. Predicados
Python permanecem apenas para explicar as poucas linhas retornadas na paginação.

Comparações de texto ignoram maiúsculas, acentos e espaços repetidos. Células vazias só
entram em `is_null`: qualquer outra comparação com elas é falsa (como no SQL).
"""

import asyncio
import hashlib
import json
import re
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.core.config import get_settings
from app.schemas.queries import (
    MAX_CONDITIONS,
    MAX_DEPTH,
    Condition,
    ConditionGroup,
    Scalar,
    StructuredQuery,
)
from app.services import storage
from app.services.datasets import (
    FALSE_VALUES,
    TRUE_VALUES,
    DatasetError,
    ParsedCsv,
    Value,
    parse_csv,
    parse_value,
)
from app.services.duckdb_cache import CACHE_VERSION, CsvCacheError, CsvDuckDBCache
from app.services.text_normalization import fold

_CANONICAL_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")
MAX_LIST_VALUES = 200
MAX_STORED_MATCHES = 50_000
CACHE_SIZE = 4
CACHE_MAX_BYTES = 128 * 1024 * 1024

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


def _as_number(column: dict, value: Scalar) -> int | float:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    # Número canônico (como no JSON) primeiro: "1234.5" não pode virar 12345 numa coluna "br".
    if _CANONICAL_NUMBER.fullmatch(text):
        return int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
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
        if kind == "integer" and (isinstance(number, int) or number.is_integer()):
            return int(number)
        return number
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
    raw_rows: Sequence[list[str | None]]
    typed_rows: Sequence[list[Value]]
    memory_bytes: int = 0


class DuckDBRows(Sequence[list[Value]]):
    """Visão paginada: os registros permanecem no disco até serem solicitados."""

    def __init__(
        self, cache: CsvDuckDBCache, columns: list[dict], count: int, *, raw: bool
    ) -> None:
        self.cache, self.columns, self.count, self.raw = cache, columns, count, raw

    def __len__(self) -> int:
        return self.count

    def fetch(self, indices: Sequence[int]) -> dict[int, list]:
        if not indices:
            return {}
        prefix = "r" if self.raw else "c"
        projection = ", ".join(f"{prefix}{i}" for i in range(len(self.columns)))
        placeholders = ", ".join("?" for _ in indices)
        try:
            rows = self.cache.consultar(
                f"SELECT _row_id, {projection} FROM dados WHERE _row_id IN ({placeholders})",
                indices,
            )
        except CsvCacheError as exc:
            raise QueryError(str(exc)) from exc
        return {row[0]: list(row[1:]) for row in rows}

    def __getitem__(self, index: int | slice) -> list[Value] | list[list[Value]]:
        if isinstance(index, slice):
            indices = list(range(*index.indices(self.count)))
            rows = self.fetch(indices)
            return [rows[i] for i in indices]
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        return self.fetch([index])[index]


CacheKey = tuple[uuid.UUID, int, tuple[tuple[str, str, str | None], ...]]
_cache: OrderedDict[CacheKey, LoadedDataset] = OrderedDict()
_loading: dict[CacheKey, asyncio.Task[LoadedDataset]] = {}
_cache_lock = asyncio.Lock()


def _key(dataset_id: uuid.UUID, size_bytes: int, columns: list[dict]) -> CacheKey:
    return dataset_id, size_bytes, tuple((c["name"], c["type"], c.get("format")) for c in columns)


def _disk_cache(key: CacheKey) -> tuple[CsvDuckDBCache, str]:
    signature = hashlib.sha256(
        json.dumps([CACHE_VERSION, str(key[0]), *key[1:]]).encode()
    ).hexdigest()
    path = get_settings().duckdb_cache_dir / f"{key[0]}-{signature[:24]}.duckdb"
    return CsvDuckDBCache(path), signature


def _open_cached(cache: CsvDuckDBCache, columns: list[dict], count: int) -> LoadedDataset:
    return LoadedDataset(
        DuckDBRows(cache, columns, count, raw=True),
        DuckDBRows(cache, columns, count, raw=False),
        memory_bytes=1024 + len(json.dumps(columns).encode()) * 2,
    )


def _persist(key: CacheKey, parsed: ParsedCsv, columns: list[dict]) -> LoadedDataset:
    try:
        cache, signature = _disk_cache(key)
        cache.importar_processado(parsed, signature)
        return _open_cached(cache, columns, len(parsed.rows))
    except CsvCacheError as exc:
        raise QueryError(str(exc)) from exc


async def _cached_load(
    key: CacheKey, loader: Callable[[], Awaitable[LoadedDataset]]
) -> LoadedDataset:
    async def fill() -> LoadedDataset:
        try:
            loaded = await loader()
            async with _cache_lock:
                if loaded.memory_bytes <= CACHE_MAX_BYTES:
                    _cache[key] = loaded
                    _cache.move_to_end(key)
                    while (
                        len(_cache) > CACHE_SIZE
                        or sum(item.memory_bytes for item in _cache.values()) > CACHE_MAX_BYTES
                    ):
                        _cache.popitem(last=False)
            return loaded
        finally:
            async with _cache_lock:
                _loading.pop(key, None)

    async with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        task = _loading.get(key)
        if task is None:
            task = asyncio.create_task(fill())
            _loading[key] = task
            # A disconnected caller must neither cancel a shared load nor leave an
            # unobserved exception when it was the last waiter.
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.shield(task)


async def prime_dataset(
    dataset_id: uuid.UUID, size_bytes: int, columns: list[dict], parsed: ParsedCsv
) -> LoadedDataset:
    """Reuse ingestion's parsed CSV instead of downloading and parsing it again."""
    return await _cached_load(
        _key(dataset_id, size_bytes, columns),
        lambda: asyncio.to_thread(_persist, _key(dataset_id, size_bytes, columns), parsed, columns),
    )


async def load_dataset(
    dataset_id: uuid.UUID, size_bytes: int, columns: list[dict]
) -> LoadedDataset:
    """Abre o .duckdb persistido; só lê o upload se o cache ainda não existe."""

    async def read() -> LoadedDataset:
        try:
            cache, signature = _disk_cache(_key(dataset_id, size_bytes, columns))
            metadata = await asyncio.to_thread(cache.metadata)
            if metadata and metadata["signature"] == signature:
                return _open_cached(cache, columns, metadata["row_count"])
            data = await storage.read_file(storage.dataset_name(dataset_id))
            parsed = await asyncio.to_thread(parse_csv, data, known_columns=columns)
            return await asyncio.to_thread(
                _persist, _key(dataset_id, size_bytes, columns), parsed, columns
            )
        except storage.StorageError as exc:
            raise QueryError("O arquivo da base não foi encontrado. Envie a base de novo.") from exc
        except (CsvCacheError, DatasetError) as exc:
            raise QueryError(str(exc)) from exc

    return await _cached_load(_key(dataset_id, size_bytes, columns), read)


def run(compiled: CompiledQuery, rows: Sequence[list[Value]]) -> list[int]:
    if isinstance(rows, DuckDBRows):
        from app.services.duckdb_sql import query_sql

        sql, parameters = query_sql(compiled.normalized, compiled.dataset)
        try:
            return [row[0] for row in rows.cache.consultar(sql, parameters)]
        except CsvCacheError as exc:
            raise QueryError(str(exc)) from exc
    predicate = compiled.predicate
    return [i for i, row in enumerate(rows) if predicate(row)]


class SQLMatches(Sequence[int]):
    """Resultado SQL com contagem total e IDs paginados, sem materializar toda a base."""

    def __init__(
        self, rows: DuckDBRows, compiled: CompiledQuery, *, prefetch_limit: int | None = None
    ) -> None:
        from app.services.duckdb_sql import query_sql

        self.cache = rows.cache
        self.sql, self.params = query_sql(compiled.normalized, compiled.dataset)
        try:
            self.total = self.cache.consultar(f"SELECT count(*) FROM ({self.sql})", self.params)[0][
                0
            ]
            # A API persiste no máximo esses IDs; as páginas seguintes são consultadas sob demanda.
            budget = MAX_STORED_MATCHES if prefetch_limit is None else prefetch_limit
            self.first = self._page(0, min(self.total, budget))
        except CsvCacheError as exc:
            raise QueryError(str(exc)) from exc

    def _page(self, start: int, stop: int) -> list[int]:
        if stop <= start:
            return []
        try:
            return [
                row[0]
                for row in self.cache.consultar(
                    f"{self.sql} LIMIT $_limit OFFSET $_offset",
                    {**self.params, "_limit": stop - start, "_offset": start},
                )
            ]
        except CsvCacheError as exc:
            raise QueryError(str(exc)) from exc

    def __len__(self) -> int:
        return self.total

    def __getitem__(self, index: int | slice) -> int | list[int]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self.total)
        else:
            if index < 0:
                index += self.total
            if not 0 <= index < self.total:
                raise IndexError(index)
            start, stop, step = index, index + 1, 1
        if step != 1:
            raise ValueError("A paginação SQL precisa de passo 1.")
        page = self.first[start:stop] if stop <= len(self.first) else self._page(start, stop)
        return page if isinstance(index, slice) else page[0]


def search(
    compiled: CompiledQuery, rows: Sequence[list[Value]], *, prefetch_limit: int | None = None
) -> Sequence[int]:
    if isinstance(rows, DuckDBRows):
        return SQLMatches(rows, compiled, prefetch_limit=prefetch_limit)
    return run(compiled, rows)


def fetch_rows(rows: Sequence, indices: Sequence[int]) -> dict[int, list]:
    """Carrega apenas uma página, em uma única consulta, sem bloquear o event loop."""
    if isinstance(rows, DuckDBRows):
        return rows.fetch(indices)
    return {i: rows[i] for i in indices}


async def delete_dataset_cache(dataset_id: uuid.UUID) -> None:
    """Remove também os dados locais após a exclusão autorizada da base."""
    async with _cache_lock:
        pending = [task for key, task in _loading.items() if key[0] == dataset_id]
    if pending:
        await asyncio.gather(*(asyncio.shield(task) for task in pending), return_exceptions=True)
    async with _cache_lock:
        for key in list(_cache):
            if key[0] == dataset_id:
                del _cache[key]

    def remove():
        from filelock import FileLock

        for path in get_settings().duckdb_cache_dir.glob(f"{dataset_id}-*.duckdb"):
            with FileLock(str(path) + ".lock", timeout=60):
                path.unlink(missing_ok=True)
                path.with_suffix(".duckdb.wal").unlink(missing_ok=True)

    await asyncio.to_thread(remove)
