"""Busca estruturada: como uma regra vira consulta a uma base de dados.

Nunca é SQL. É um JSON com a base, as condições (coluna, operador, valor) e como elas se
combinam; antes de rodar, `services.query_engine` confere tudo contra o schema da base.

Exemplo:
    {"dataset": "contratos", "logic": "and", "conditions": [
        {"column": "Valor", "op": "gt", "value": 17600},
        {"logic": "or", "conditions": [
            {"column": "Modalidade", "op": "eq", "value": "Dispensa"},
            {"column": "Modalidade", "op": "eq", "value": "Inexigibilidade"}]}]}
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Operator = Literal[
    "eq",  # igual
    "ne",  # diferente
    "gt",  # maior que
    "gte",  # maior ou igual
    "lt",  # menor que
    "lte",  # menor ou igual
    "between",  # entre dois valores, inclusive: value = [mínimo, máximo]
    "in",  # é um dos valores: value = [...]
    "not_in",  # não é nenhum dos valores
    "contains",  # texto contém
    "not_contains",  # texto não contém
    "starts_with",  # texto começa com
    "ends_with",  # texto termina com
    "is_null",  # célula vazia (sem value)
    "not_null",  # célula preenchida (sem value)
]
Scalar = str | int | float | bool
QueryState = Literal["pendente", "ok", "erro"]
QueryOrigin = Literal["ia", "manual"]
Verdict = Literal["segue", "viola"]

MAX_CONDITIONS = 30
MAX_DEPTH = 3


class Condition(BaseModel):
    # Sem campos extras: é isso que separa uma condição de um grupo na união abaixo.
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=200)
    op: Operator
    value: Scalar | list[Scalar] | None = Field(
        default=None,
        description="Valor comparado; lista em between (2 itens), in e not_in; vazio em "
        "is_null e not_null. Datas em AAAA-MM-DD.",
    )


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logic: Literal["and", "or"] = Field(default="and", description="and = todas; or = qualquer")
    conditions: list["Condition | ConditionGroup"] = Field(default_factory=list)


class StructuredQuery(ConditionGroup):
    """Sem condições, a busca devolve todos os registros da base."""

    dataset: str = Field(min_length=1, max_length=200, description="Nome da base na análise.")


class RuleQueryOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID | None = Field(description="Nulo se a base foi removida.")
    dataset_name: str | None
    query: StructuredQuery
    origin: QueryOrigin
    state: QueryState = Field(description="pendente (não rodou), ok ou erro (ver `error`).")
    error: str | None
    match_count: int | None = Field(description="Registros encontrados na última execução.")
    executed_at: datetime | None
    verdict: Verdict | None = Field(description="Reservado para a verificação (segue/viola).")
    verdict_details: dict | None


class RecordsOut(BaseModel):
    dataset_id: uuid.UUID
    dataset_name: str
    columns: list[str]
    total: int = Field(description="Total de registros encontrados pela busca.")
    offset: int
    rows: list["RecordRow"]


class RecordRow(BaseModel):
    index: int = Field(description="Linha no CSV (0 = primeira linha depois do cabeçalho).")
    values: list[str | None]
