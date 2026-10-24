"""Bases de dados em CSV: leitura, schema inferido e valores tipados.

O CSV original fica no storage; o banco guarda só o schema (colunas, tipos e exemplos) e
algumas linhas de amostra, que vão como contexto para a IA. A mesma inferência é usada
depois para converter as linhas na hora de rodar as buscas das regras.
"""

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import PurePath

COLUMN_TYPES = ("integer", "decimal", "date", "datetime", "boolean", "text")
DELIMITERS = (",", ";", "\t", "|")
SAMPLE_ROWS = 10
MAX_EXAMPLES = 5
# Colunas de texto com poucos valores distintos (categorias) mandam a lista inteira à IA,
# para a busca usar exatamente os valores que existem na base.
MAX_CATEGORY_VALUES = 30
MAX_DISTINCT_TRACKED = 1000
MAX_CELL_CHARS = 10_000

TRUE_VALUES = {"true", "sim", "verdadeiro", "yes"}
FALSE_VALUES = {"false", "não", "nao", "falso", "no"}

_INTEGER = re.compile(r"^[+-]?\d+$")
# 1.234,56 (padrão brasileiro) e 1,234.56 (padrão americano); milhar opcional.
_NUMBER_BR = re.compile(r"^[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$")
_NUMBER_US = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_DATE_FORMATS = {"iso": "%Y-%m-%d", "br": "%d/%m/%Y"}
_DATETIME_FORMATS = {
    "iso": ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"),
    "br": ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"),
}

Value = int | float | date | datetime | bool | str | None


class DatasetError(Exception):
    """CSV inválido, com mensagem em português para a pessoa."""


@dataclass
class ColumnInfo:
    name: str
    type: str
    # Números: "br" ou "us"; datas: "iso" ou "br"; demais tipos: None.
    format: str | None
    null_count: int
    # Limitado a MAX_DISTINCT_TRACKED (valores acima disso aparecem como o limite).
    distinct_count: int
    examples: list[str] = field(default_factory=list)
    # Todos os valores distintos, quando é uma coluna de categorias (texto); senão vazio.
    values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedCsv:
    encoding: str
    delimiter: str
    columns: list[ColumnInfo]
    # Células como texto (sem espaços nas pontas), None quando vazias.
    rows: list[list[str | None]]

    @property
    def sample_rows(self) -> list[list[str | None]]:
        return self.rows[:SAMPLE_ROWS]


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def decode(data: bytes) -> tuple[str, str]:
    """Texto e codificação. Planilhas exportadas no Windows costumam vir em cp1252."""
    if data.startswith(b"PK\x03\x04"):
        raise DatasetError("Este arquivo parece ser do Excel. Salve a planilha como CSV.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        encoding, text = "latin-1", data.decode("latin-1")
    if "\x00" in text:
        raise DatasetError("O arquivo não parece ser um CSV de texto.")
    return text, "utf-8" if encoding == "utf-8-sig" else encoding


def detect_delimiter(text: str) -> str:
    """Separador que divide as primeiras linhas no mesmo número (maior que 1) de colunas."""
    sample = "\n".join(text[:65_536].splitlines()[:50])
    best, best_score = ",", (0.0, 0)
    for delimiter in DELIMITERS:
        try:
            rows = [r for r in csv.reader(io.StringIO(sample), delimiter=delimiter) if r]
        except csv.Error:
            continue
        # A última linha da amostra pode ter sido cortada no meio.
        widths = [len(r) for r in (rows[:-1] if len(rows) > 1 else rows)]
        if not widths or widths[0] < 2:
            continue
        consistency = sum(w == widths[0] for w in widths) / len(widths)
        score = (consistency, widths[0])
        if score > best_score:
            best, best_score = delimiter, score
    return best


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _header(raw: list[str]) -> list[str]:
    """Nomes das colunas, sem vazios nem repetidos."""
    names: list[str] = []
    for index, name in enumerate(raw):
        name = " ".join(name.split()) or f"coluna_{index + 1}"
        candidate, n = name, 2
        while candidate in names:
            candidate, n = f"{name}_{n}", n + 1
        names.append(candidate)
    return names


def parse_csv(data: bytes, *, max_rows: int, max_columns: int) -> ParsedCsv:
    text, encoding = decode(data)
    if not text.strip():
        raise DatasetError("O arquivo está vazio.")
    delimiter = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    csv.field_size_limit(MAX_CELL_CHARS * 10)

    header: list[str] | None = None
    rows: list[list[str | None]] = []
    try:
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue
            if header is None:
                header = _header(raw)
                if len(header) > max_columns:
                    raise DatasetError(
                        f"A base tem {len(header)} colunas; o limite é {max_columns}."
                    )
                continue
            if len(raw) > len(header):
                # Células vazias sobrando no fim da linha (comum em planilhas) não contam.
                extra = raw[len(header) :]
                if any(cell.strip() for cell in extra):
                    raise DatasetError(
                        f"A linha {reader.line_num} tem {len(raw)} colunas, mas o cabeçalho "
                        f"tem {len(header)}. Confira o separador e as aspas do arquivo."
                    )
                raw = raw[: len(header)]
            if len(rows) >= max_rows:
                raise DatasetError(f"A base passa do limite de {_thousands(max_rows)} linhas.")
            cells: list[str | None] = [(cell.strip() or None) for cell in raw]
            cells.extend([None] * (len(header) - len(cells)))
            rows.append(cells)
    except csv.Error as exc:
        raise DatasetError(
            f"Não foi possível ler o CSV (linha {reader.line_num}). Confira as aspas do arquivo."
        ) from exc

    if header is None:
        raise DatasetError("O arquivo está vazio.")
    if not rows:
        raise DatasetError("A base só tem o cabeçalho, sem nenhuma linha de dados.")
    if any(cell and len(cell) > MAX_CELL_CHARS for row in rows for cell in row):
        raise DatasetError(f"Há células com mais de {_thousands(MAX_CELL_CHARS)} caracteres.")

    prefer = "br" if delimiter == ";" else "us"
    columns = [
        infer_column(name, [row[i] for row in rows], prefer) for i, name in enumerate(header)
    ]
    return ParsedCsv(encoding=encoding, delimiter=delimiter, columns=columns, rows=rows)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


def _strip_currency(value: str) -> str:
    return value[2:].strip() if value.startswith("R$") else value


def _number_type(values: list[str], prefer: str) -> tuple[str, str] | None:
    plain = [_strip_currency(v) for v in values]
    br = all(_NUMBER_BR.match(v) for v in plain)
    us = all(_NUMBER_US.match(v) for v in plain)
    if not (br or us):
        return None
    # "1.500" serve nos dois padrões; o separador do arquivo desempata.
    fmt = "br" if br and (not us or prefer == "br") else "us"
    decimal_mark = "," if fmt == "br" else "."
    kind = "decimal" if any(decimal_mark in v for v in plain) else "integer"
    return kind, fmt


def _parses(values: list[str], formats: tuple[str, ...]) -> bool:
    for value in values:
        for fmt in formats:
            try:
                datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            return False
    return True


def infer_column(name: str, cells: list[str | None], prefer: str = "us") -> ColumnInfo:
    values = [c for c in cells if c is not None]
    null_count = len(cells) - len(values)
    distinct: dict[str, None] = {}
    for value in values:
        if len(distinct) >= MAX_DISTINCT_TRACKED:
            break
        distinct.setdefault(value, None)
    examples = list(distinct)[:MAX_EXAMPLES]

    def info(type_: str, fmt: str | None = None) -> ColumnInfo:
        is_category = type_ in ("text", "boolean") and len(distinct) <= MAX_CATEGORY_VALUES
        categories = sorted(distinct) if is_category else []
        return ColumnInfo(name, type_, fmt, null_count, len(distinct), examples, categories)

    if not values:
        return info("text")
    # Zeros à esquerda (CEP, códigos) indicam identificador, não número.
    leading_zero = any(len(v) > 1 and v[0] == "0" and v[1].isdigit() for v in values)
    if not leading_zero:
        if all(_INTEGER.match(v) for v in values):
            return info("integer", None)
        number = _number_type(values, prefer)
        if number:
            return info(*number)
    lower = {v.lower() for v in distinct}
    if lower <= TRUE_VALUES | FALSE_VALUES:
        return info("boolean")
    for fmt, pattern in _DATE_FORMATS.items():
        if _parses(values, (pattern,)):
            return info("date", fmt)
    for fmt, patterns in _DATETIME_FORMATS.items():
        if _parses(values, patterns):
            return info("datetime", fmt)
    return info("text")


def parse_value(column: dict, raw: str | None) -> Value:
    """Converte uma célula para o tipo da coluna (o dict de `ColumnInfo`).

    Uma célula que não bate com o tipo (o que não acontece com o schema inferido do
    próprio arquivo) vira None, em vez de derrubar a busca inteira.
    """
    if raw is None:
        return None
    type_, fmt = column["type"], column.get("format")
    try:
        if type_ == "integer" or type_ == "decimal":
            text = _strip_currency(raw)
            if fmt == "br":
                text = text.replace(".", "").replace(",", ".")
            elif fmt == "us":
                text = text.replace(",", "")
            return int(text) if type_ == "integer" else float(text)
        if type_ == "boolean":
            lower = raw.lower()
            return True if lower in TRUE_VALUES else False if lower in FALSE_VALUES else None
        if type_ == "date":
            return datetime.strptime(raw, _DATE_FORMATS[fmt or "iso"]).date()
        if type_ == "datetime":
            for pattern in _DATETIME_FORMATS[fmt or "iso"]:
                try:
                    return datetime.strptime(raw, pattern)
                except ValueError:
                    continue
            return None
    except (ValueError, KeyError):
        return None
    return raw


def dataset_display_name(filename: str, taken: set[str]) -> str:
    """Nome da base a partir do arquivo, único dentro da análise."""
    base = " ".join(PurePath(filename).stem.split())[:80] or "base"
    name, n = base, 2
    while name in taken:
        name, n = f"{base} ({n})", n + 1
    return name
