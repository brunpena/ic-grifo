import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.documents import DocumentOut
from app.schemas.validation import ColumnMeaning

ColumnType = Literal["integer", "decimal", "date", "datetime", "boolean", "text"]


class DatasetColumn(BaseModel):
    semantic: ColumnMeaning | None = Field(
        default=None, description="Significado interpretado pela IA."
    )
    name: str
    type: ColumnType = Field(description="Tipo inferido a partir de todos os valores da coluna.")
    format: str | None = Field(
        description="Números: br (1.234,56) ou us (1,234.56). Datas: iso ou br (dd/mm/aaaa)."
    )
    null_count: int = Field(description="Células vazias.")
    distinct_count: int = Field(description="Valores distintos (contados até 1.000).")
    examples: list[str]
    values: list[str] = Field(
        description="Todos os valores distintos, em colunas de categorias (até 30); senão vazio."
    )


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    name: str = Field(description="Nome único na análise, usado pela IA para citar a base.")
    filename: str
    size_bytes: int
    original_size_bytes: int | None = None
    status: Literal["processing", "ready", "error"] = Field(
        description="processing: lendo a base no servidor; só bases `ready` entram nas buscas."
    )
    status_message: str | None = Field(description="Motivo, quando `error`.")
    encoding: str
    delimiter: str
    row_count: int
    columns: list[DatasetColumn]
    created_at: datetime


class AnalysisCreateIn(BaseModel):
    title: str = Field(default="Nova análise", max_length=200)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return value.strip() or "Nova análise"


class AnalysisUpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AnalysisOut(BaseModel):
    id: uuid.UUID
    title: str
    dataset_count: int
    document_count: int
    created_at: datetime


class AnalysisDetailOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    datasets: list[DatasetOut]
    documents: list[DocumentOut]
