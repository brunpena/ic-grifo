"""Contrato da interpretação de colunas e da verificação de regras nos CSVs."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.queries import Operator, Scalar, StructuredQuery


class ColumnMeaning(BaseModel):
    meaning: str = Field(max_length=600)
    semantic_type: Literal[
        "identifier",
        "amount",
        "date",
        "duration",
        "status",
        "category",
        "boolean",
        "text",
        "unknown",
    ] = "unknown"
    event: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=80)
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str = Field(default="", max_length=600)


class Operand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "column", "literal", "days_between", "ratio_percent", "percentage", "deadline", "today"
    ]
    column: str | None = None
    other_column: str | None = None
    value: Scalar | list[Scalar] | None = None
    unit: Literal["days", "months", "years"] = "days"


class ComplianceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: Operand
    op: Operator
    right: Operand | None = None
    explanation: str = Field(min_length=1, max_length=600)


class DatasetCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: StructuredQuery
    logic: Literal["and", "or"] = "and"
    checks: list[ComplianceCheck] = Field(min_length=1, max_length=30)


class ValidationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=1, max_length=1200)
    missing_data: list[str] = Field(default_factory=list, max_length=30)
    datasets: list[DatasetCheck] = Field(default_factory=list, max_length=20)


ValidationStatus = Literal[
    "conforme", "violacao", "inconclusiva", "nao_aplicavel", "erro", "desatualizada", "ignorada"
]
RecordVerdict = Literal["conforme", "violacao", "inconclusiva"]


class ValidationCounts(BaseModel):
    applicable_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    unknown_count: int = 0


class DatasetValidation(ValidationCounts):
    dataset_id: uuid.UUID
    dataset_name: str
    explanation: str = ""


class RuleValidationOut(ValidationCounts):
    status: ValidationStatus
    explanation: str
    checked_at: datetime
    missing_data: list[str] = Field(default_factory=list)
    datasets: list[DatasetValidation] = Field(default_factory=list)


class ValidationRecord(BaseModel):
    index: int
    values: list[str | None]
    verdict: RecordVerdict
    explanation: str


class ValidationRecordsOut(BaseModel):
    dataset_id: uuid.UUID
    dataset_name: str
    columns: list[str]
    total: int
    offset: int
    rows: list[ValidationRecord]
