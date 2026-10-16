import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RuleType = Literal["obrigacao", "proibicao", "prazo", "condicao", "outro"]
RuleStatus = Literal["pendente", "validada", "rejeitada"]
DocumentStatus = Literal["processing", "extracting_rules", "ready", "error"]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: DocumentStatus = Field(
        description="processing (lendo o PDF), extracting_rules (IA analisando), ready ou error."
    )
    status_message: str | None = Field(description="Progresso ou motivo do erro, em português.")
    page_count: int | None
    created_at: datetime


class HighlightBox(BaseModel):
    """Retângulo do grifo, em frações da página (0 a 1), origem no canto superior esquerdo."""

    page: int
    x: float
    y: float
    width: float
    height: float


class RuleOut(BaseModel):
    id: uuid.UUID
    type: RuleType
    status: RuleStatus
    summary: str
    excerpt: str
    comment: str | None
    origin: Literal["ia", "manual"]
    page: int | None = Field(description="Página onde o trecho começa.")
    boxes: list[HighlightBox]


class RuleCreateIn(BaseModel):
    type: RuleType
    summary: str = Field(min_length=1, max_length=200)
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=2, max_length=5000, description="Texto selecionado na página.")

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("informe o resumo")
        return value


class RuleUpdateIn(BaseModel):
    type: RuleType | None = None
    status: RuleStatus | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)


class CitedRule(BaseModel):
    id: uuid.UUID
    type: RuleType
    summary: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str = Field(description="Texto sem os marcadores de citação [R1].")
    citations: list[CitedRule]
    created_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
