"""Modelos do banco. Offsets de caracteres são guardados em code points (padrão do Python);
a conversão para UTF-16 acontece só na borda da API (ver `app.core.offsets`)."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim

SOURCE_TYPES = ("pdf", "text", "html", "url")
MODES = ("assistant", "knowledge_base")
DOCUMENT_STATUSES = ("processing", "extracting_rules", "ready", "error")
DATASET_STATUSES = ("processing", "ready", "error")
RULE_TYPES = ("obrigacao", "proibicao", "prazo", "condicao", "outro")
RULE_STATUSES = ("pendente", "validada", "rejeitada")
RULE_ORIGINS = ("ia", "manual")
MESSAGE_ROLES = ("user", "assistant")
QUERY_ORIGINS = ("ia", "manual")
QUERY_STATES = ("pendente", "ok", "erro")
# Resultado da verificação da regra contra os registros (página de violações, futura).
VERDICTS = ("segue", "viola")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    """Uma análise: as bases de dados (CSV) verificadas e os documentos de onde saem as regras."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nulo apenas em análises criadas para documentos anteriores ao login.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Dataset.created_at",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Document.created_at",
    )


class Dataset(Base):
    """Base de dados enviada em CSV. O arquivo fica no storage e só é lido no back, pelas
    buscas das regras; aqui ficam o schema e a situação da leitura."""

    __tablename__ = "datasets"
    __table_args__ = (
        Index("ix_datasets_analysis_id", "analysis_id"),
        CheckConstraint(_in("status", DATASET_STATUSES), name="ck_datasets_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    # Nome único na análise; é como a IA se refere à base nas buscas.
    name: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    original_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # processing: arquivo guardado, schema sendo detectado em segundo plano.
    status: Mapped[str] = mapped_column(Text, default="processing")
    status_message: Mapped[str | None] = mapped_column(Text)
    # Detectados na leitura; vazios enquanto `processing`.
    encoding: Mapped[str] = mapped_column(Text, default="")
    delimiter: Mapped[str] = mapped_column(Text, default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    # [{name, type, format, null_count, distinct_count, examples, values}] (ver services.datasets)
    columns: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="datasets")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in("source_type", SOURCE_TYPES), name="ck_documents_source_type"),
        CheckConstraint(_in("mode", MODES), name="ck_documents_mode"),
        CheckConstraint(_in("status", DOCUMENT_STATUSES), name="ck_documents_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Dono do documento; nulo apenas em documentos anteriores ao login.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)
    # Endereço de origem, quando o documento veio de um link.
    source_url: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    full_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="processing")
    status_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="documents")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.page_number"
    )


class Page(Base):
    __tablename__ = "pages"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    page_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)

    document: Mapped[Document] = relationship(back_populates="pages")


class Word(Base):
    """Uma palavra (ou fragmento visual dela) com posição na página.

    Uma palavra hifenizada no fim da linha vira uma única palavra em `full_text`, mas é
    guardada como duas linhas aqui, com o mesmo `text`/`char_start`/`char_end` e um bbox cada.
    """

    __tablename__ = "words"
    __table_args__ = (
        Index("ix_words_document_page", "document_id", "page"),
        Index("ix_words_document_char_start", "document_id", "char_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    x0: Mapped[float] = mapped_column(Float)
    y0: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint(_in("type", RULE_TYPES), name="ck_rules_type"),
        CheckConstraint(_in("status", RULE_STATUSES), name="ck_rules_status"),
        CheckConstraint(_in("origin", RULE_ORIGINS), name="ck_rules_origin"),
        CheckConstraint("char_end > char_start", name="ck_rules_range"),
        Index("ix_rules_document_char_start", "document_id", "char_start"),
        Index(
            "ix_rules_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="pendente")
    comment: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    # Bases da análise que a IA relacionou à regra (a busca é gerada só para essas).
    dataset_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, server_default="{}"
    )
    # Plano gerado pela IA e resultado calculado sobre todas as linhas aplicáveis.
    validation: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuleQuery(Base):
    """A busca estruturada que transforma uma regra em consulta a uma base de dados.

    `query` segue o formato de `app.schemas.queries.StructuredQuery` e é sempre validada
    contra o schema da base antes de rodar. Os registros encontrados são guardados pelo
    índice da linha no CSV (0 = primeira linha depois do cabeçalho).
    """

    __tablename__ = "rule_queries"
    __table_args__ = (
        CheckConstraint(_in("origin", QUERY_ORIGINS), name="ck_rule_queries_origin"),
        CheckConstraint(_in("state", QUERY_STATES), name="ck_rule_queries_state"),
        CheckConstraint(
            f"verdict IS NULL OR {_in('verdict', VERDICTS)}", name="ck_rule_queries_verdict"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), unique=True
    )
    # Nulo se a base foi excluída depois de a busca ser gerada.
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), index=True
    )
    query: Mapped[dict] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(Text)
    # pendente (ainda não rodou), ok ou erro (ver `error`).
    state: Mapped[str] = mapped_column(Text, default="pendente")
    error: Mapped[str | None] = mapped_column(Text)
    match_count: Mapped[int | None] = mapped_column(Integer)
    matched_rows: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}"
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Preparado para a página de violações: segue/viola e os detalhes da verificação.
    verdict: Mapped[str | None] = mapped_column(Text)
    verdict_details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(_in("role", MESSAGE_ROLES), name="ck_messages_role"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    rule_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    # Sempre em minúsculas (ver `normalize_email`), por isso a unicidade é simples.
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSession(Base):
    """Sessão de login. Guarda só o hash do token; o token em si fica no cookie do navegador."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")
