"""Cache CSV persistente em DuckDB embarcado, sem servidor ou conexão global.

Cada operação fecha sua conexão antes de liberar o lock entre processos. Isso permite
usar o mesmo arquivo em vários workers, serializando o acesso por arquivo (inclusive
leituras), e evita misturar leitores read_only com um escritor de outro processo.
"""

import csv
import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import duckdb
from filelock import FileLock, Timeout

from app.services.datasets import DatasetError, ParsedCsv, parse_csv, parse_value
from app.services.text_normalization import fold

CACHE_VERSION = 1
SQL_TYPES = {
    "integer": "HUGEINT",
    "decimal": "DOUBLE",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "boolean": "BOOLEAN",
    "text": "VARCHAR",
}


class CsvCacheError(Exception):
    """Falha de leitura, sincronização ou consulta do cache local."""


class CsvDuckDBCache:
    """Uma base CSV por arquivo .duckdb. Os valores das consultas usam parâmetros."""

    def __init__(self, caminho_banco: str | Path) -> None:
        try:
            self.path = Path(caminho_banco).expanduser().resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CsvCacheError(f"Não foi possível criar a pasta do cache: {exc}") from exc

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        try:
            with FileLock(str(self.path) + ".lock", timeout=60):
                with duckdb.connect(str(self.path), read_only=not write) as connection:
                    if not write:
                        connection.execute("SET enable_external_access = false")
                    yield connection
        except Timeout as exc:
            raise CsvCacheError(
                "Tempo esgotado aguardando o cache local. Tente novamente."
            ) from exc
        except (duckdb.Error, OSError) as exc:
            raise CsvCacheError(f"Não foi possível acessar o cache DuckDB: {exc}") from exc

    @staticmethod
    def _metadata(connection: duckdb.DuckDBPyConnection) -> dict | None:
        exists = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = '_cache_metadata'"
        ).fetchone()[0]
        if not exists:
            return None
        row = connection.execute(
            "SELECT signature, columns_json, row_count, version FROM _cache_metadata"
        ).fetchone()
        if not row or row[3] != CACHE_VERSION:
            return None
        return {"signature": row[0], "columns": json.loads(row[1]), "row_count": row[2]}

    def metadata(self) -> dict | None:
        if not self.path.exists():
            return None
        with self._connection() as connection:
            return self._metadata(connection)

    def sincronizar_csv(self, caminho_csv: str | Path, forcar_atualizacao: bool = False) -> bool:
        """Retorna True se importou. Cache válido só consulta stat(), sem reler o CSV.

        A assinatura usa caminho absoluto, tamanho e mtime_ns. Se uma ferramenta
        preservar ambos ao alterar o arquivo, use forcar_atualizacao=True.
        """
        source = Path(caminho_csv).expanduser().resolve()
        try:
            before = source.stat()
            signature = json.dumps([str(source), before.st_size, before.st_mtime_ns])
            with self._connection(write=True) as connection:
                metadata = self._metadata(connection)
                if not forcar_atualizacao and metadata and metadata["signature"] == signature:
                    return False
                parsed = parse_csv(source.read_bytes())
                after = source.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise CsvCacheError("O CSV mudou durante a importação. Tente novamente.")
                self._import(connection, parsed, signature)
            return True
        except (OSError, DatasetError) as exc:
            raise CsvCacheError(f"Não foi possível importar o CSV: {exc}") from exc

    def importar_processado(self, parsed: ParsedCsv, signature: str) -> None:
        """Reaproveita o parser do upload; não baixa nem abre o CSV novamente."""
        with self._connection(write=True) as connection:
            metadata = self._metadata(connection)
            if not metadata or metadata["signature"] != signature:
                self._import(connection, parsed, signature)

    def _import(
        self, connection: duckdb.DuckDBPyConnection, parsed: ParsedCsv, signature: str
    ) -> None:
        from app.services.query_engine import coerce

        columns = [c.to_dict() for c in parsed.columns]
        definitions = ["_row_id BIGINT PRIMARY KEY"]
        for index, column in enumerate(columns):
            definitions.extend(
                [
                    f"c{index} {SQL_TYPES[column['type']]}",
                    f"r{index} VARCHAR",
                    f"f{index} VARCHAR",
                    f"p{index} DOUBLE",
                ]
            )
        # COPY faz uma carga vetorizada; executemany por registro é muito mais lento.
        # O arquivo temporário contém valores já normalizados e é sempre removido.
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                suffix=".csv",
                delete=False,
                dir=self.path.parent,
            ) as handle:
                temporary = Path(handle.name)
                writer = csv.writer(handle)
                for row_id, row in enumerate(parsed.rows):
                    record: list[Any] = [row_id]
                    for column, raw in zip(columns, row, strict=True):
                        typed = parse_value(column, raw)
                        percent = None
                        if column["type"] == "text" and raw and raw.endswith("%"):
                            # Mesma conversão usada por compliance.coerce, só na importação.
                            try:
                                percent = coerce(
                                    {"type": "decimal", "format": column.get("format")},
                                    raw[:-1].strip(),
                                )
                            except ValueError:
                                pass
                        folded = fold(raw) if raw is not None and column["type"] == "text" else None
                        record.extend([typed, raw, folded, percent])
                    writer.writerow(record)
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(f"CREATE OR REPLACE TABLE dados ({', '.join(definitions)})")
                filename = str(temporary).replace("'", "''")
                connection.execute(f"COPY dados FROM '{filename}' (FORMAT CSV, HEADER false)")
                # ID exato é uma busca comum; índices ART servem a esse acesso seletivo.
                for index, column in enumerate(columns):
                    if fold(column["name"]) == "id":
                        connection.execute(f"CREATE INDEX idx_id ON dados(c{index})")
                        if column["type"] == "text":
                            connection.execute(f"CREATE INDEX idx_id_folded ON dados(f{index})")
                        break
                connection.execute(
                    "CREATE OR REPLACE TABLE _cache_metadata "
                    "(signature VARCHAR, columns_json VARCHAR, "
                    "row_count BIGINT, version INTEGER)"
                )
                connection.execute(
                    "INSERT INTO _cache_metadata VALUES (?, ?, ?, ?)",
                    [
                        signature,
                        json.dumps(columns, ensure_ascii=False),
                        len(parsed.rows),
                        CACHE_VERSION,
                    ],
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def consultar(
        self, sql: str, parametros: Sequence[Any] | Mapping[str, Any] = ()
    ) -> list[tuple]:
        """SQL interno, gerado pelo compilador. Nunca passar SQL livre vindo da IA/UI.

        A conexão somente leitura também desabilita acesso a arquivos e rede.
        """
        with self._connection() as connection:
            parameters = dict(parametros) if isinstance(parametros, Mapping) else list(parametros)
            return connection.execute(sql, parameters).fetchall()

    def _column_index(self, name: str) -> tuple[int, dict, list[dict]]:
        metadata = self.metadata()
        if metadata is None:
            raise CsvCacheError("Sincronize um CSV antes de consultar o cache.")
        columns = metadata["columns"]
        for index, column in enumerate(columns):
            if column["name"] == name:
                return index, column, columns
        raise CsvCacheError(f"A coluna “{name}” não existe no CSV.")

    def buscar_por_id(self, valor: str | int, coluna: str = "id") -> dict | None:
        """Primeiro registro na ordem do CSV. IDs duplicados não são descartados."""
        index, column, columns = self._column_index(coluna)
        typed = parse_value(column, str(valor))
        if typed is None:
            raise CsvCacheError(f"ID incompatível com o tipo da coluna “{coluna}”.")
        projection = ", ".join(f"c{i}" for i in range(len(columns)))
        target = "CAST(? AS HUGEINT)" if column["type"] == "integer" else "?"
        rows = self.consultar(
            f"SELECT {projection} FROM dados WHERE c{index} = {target} ORDER BY _row_id LIMIT 1",
            [str(typed) if column["type"] == "integer" else typed],
        )
        return dict(zip([c["name"] for c in columns], rows[0], strict=True)) if rows else None

    def buscar_texto(
        self,
        coluna: str,
        texto: str,
        *,
        limite: int = 100,
        offset: int = 0,
        ignorar_maiusculas: bool = True,
    ) -> list[dict]:
        """Busca parcial literal: % e _ no texto não viram curingas de SQL."""
        if not 1 <= limite <= 1000 or offset < 0:
            raise CsvCacheError("Use limite entre 1 e 1.000 e offset não negativo.")
        index, column, columns = self._column_index(coluna)
        if column["type"] != "text":
            raise CsvCacheError("A busca parcial precisa de uma coluna de texto.")
        pattern = "%" + texto.replace("$", "$$").replace("%", "$%").replace("_", "$_") + "%"
        operator = "ILIKE" if ignorar_maiusculas else "LIKE"
        projection = ", ".join(f"c{i}" for i in range(len(columns)))
        rows = self.consultar(
            f"SELECT {projection} FROM dados WHERE c{index} {operator} ? ESCAPE '$' "
            "ORDER BY _row_id LIMIT ? OFFSET ?",
            [pattern, limite, offset],
        )
        return [dict(zip([c["name"] for c in columns], row, strict=True)) for row in rows]


if __name__ == "__main__":
    # python -m app.services.duckdb_cache contratos.csv cache/contratos.duckdb
    import sys

    cache = CsvDuckDBCache(sys.argv[2])
    print("Importou:", cache.sincronizar_csv(sys.argv[1]))
    print("ID:", cache.buscar_por_id("001", coluna="id"))
    print("Texto:", cache.buscar_texto("Fornecedor", "Alfa", limite=20))
