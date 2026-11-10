import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.queries import RuleQueryOut, StructuredQuery
from app.schemas.validation import RuleValidationOut

RuleType = Literal["obrigacao", "proibicao", "prazo", "condicao", "outro"]
RuleStatus = Literal["pendente", "validada", "rejeitada"]
RuleCategory = Literal["csv", "geral"]
DocumentStatus = Literal["processing", "extracting_rules", "ready", "error"]
SourceType = Literal["pdf", "text", "html", "url"]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    title: str
    source_type: SourceType = Field(description="Como o documento foi enviado.")
    source_url: str | None = Field(description="Endereço de origem, se veio de um link.")
    status: DocumentStatus = Field(
        description="processing (lendo o PDF), extracting_rules (validação geral em "
        "andamento), ready (pronto para grifar) ou error."
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
    validation: RuleValidationOut | None = None
    id: uuid.UUID
    type: RuleType
    status: RuleStatus
    summary: str
    excerpt: str
    comment: str | None
    origin: Literal["ia", "manual"]
    category: RuleCategory = Field(
        description="csv: verificável nas bases (tem busca); geral: registrada sem busca."
    )
    interpretation: str | None = Field(description="Como a regra foi interpretada e aprovada.")
    page: int | None = Field(description="Página onde o trecho começa.")
    boxes: list[HighlightBox]
    dataset_ids: list[uuid.UUID] = Field(description="Bases da análise usadas pela busca.")
    query: RuleQueryOut | None = Field(description="Busca da regra nas bases, se houver.")


class RuleCreateIn(BaseModel):
    """Aprovação de uma regra: só aqui ela entra no banco, já validada pela pessoa."""

    type: RuleType
    summary: str = Field(min_length=1, max_length=200)
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=2, max_length=5000, description="Texto grifado na página.")
    category: RuleCategory = Field(
        default="geral",
        description="csv exige `query`; geral guarda a regra sem busca nas bases.",
    )
    interpretation: str | None = Field(default=None, max_length=4000)
    origin: Literal["ia", "manual"] = Field(
        default="manual", description="ia quando a proposta da IA foi aprovada."
    )
    query: StructuredQuery | None = Field(
        default=None, description="Busca revisada pela pessoa (obrigatória em csv)."
    )

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("informe o resumo")
        return value

    @field_validator("interpretation")
    @classmethod
    def _interpretation(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class RuleUpdateIn(BaseModel):
    type: RuleType | None = None
    status: RuleStatus | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)
    interpretation: str | None = Field(default=None, max_length=4000)


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


class TextDocumentIn(BaseModel):
    analysis_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, description="Texto do documento.")

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("content")
    @classmethod
    def _content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cole o texto do documento")
        return value


class UrlDocumentIn(BaseModel):
    analysis_id: uuid.UUID | None = None
    url: str = Field(min_length=1, max_length=2000, description="Link http(s) do PDF ou da página.")


class ExcerptMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class RuleProposalIn(BaseModel):
    """A proposta como está na tela (a pessoa pode tê-la editado antes de pedir ajustes)."""

    category: RuleCategory
    type: RuleType
    summary: str = Field(default="", max_length=200)
    interpretation: str = Field(default="", max_length=4000)
    query: StructuredQuery | None = None


class ExcerptAnalysisIn(BaseModel):
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=2, max_length=5000, description="Texto grifado na página.")
    messages: list[ExcerptMessage] = Field(
        default_factory=list,
        max_length=30,
        description="Conversa até aqui, terminando na mensagem da pessoa. Vazia na abertura.",
    )
    current: RuleProposalIn | None = Field(
        default=None, description="Proposta atual, para a IA ajustá-la em vez de recomeçar."
    )


class RuleProposal(BaseModel):
    """O que a IA propõe para o trecho. Nada é salvo até a aprovação (POST /rules)."""

    is_rule: bool = Field(description="O trecho tem força normativa.")
    category: RuleCategory = Field(description="csv: verificável nas bases; geral: não.")
    type: RuleType
    summary: str
    interpretation: str
    reason: str = Field(description="Por que a regra é (ou não) verificável nos dados.")
    query: StructuredQuery | None = Field(description="Busca proposta, só em csv.")
    sql_display: str | None = Field(description="SQL legível da busca, para revisão.")
    match_count: int | None = Field(description="Registros que a busca encontra hoje.")
    query_error: str | None = Field(
        description="Problema da busca proposta (coluna ou valor inválido), para corrigir."
    )


class ExcerptAnalysisOut(BaseModel):
    reply: str = Field(description="Mensagem da IA para a pessoa.")
    proposal: RuleProposal


class QueryPreviewOut(BaseModel):
    query: StructuredQuery = Field(description="A busca com nomes e tipos normalizados.")
    dataset_id: uuid.UUID
    sql_display: str | None
    match_count: int
