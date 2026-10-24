"""Análises, bases de dados (CSV) e a busca estruturada de cada regra.

Cada documento existente vira uma análise com um documento só (mesmo id e título).

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"])

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text()),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("encoding", sa.Text(), nullable=False),
        sa.Column("delimiter", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("sample_rows", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_datasets_analysis_id", "datasets", ["analysis_id"])

    op.add_column(
        "documents",
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
        ),
    )
    op.add_column("documents", sa.Column("source_url", sa.Text()))
    op.execute(
        "INSERT INTO analyses (id, user_id, title, created_at) "
        "SELECT id, user_id, title, created_at FROM documents"
    )
    op.execute("UPDATE documents SET analysis_id = id")
    op.alter_column("documents", "analysis_id", nullable=False)
    op.create_index("ix_documents_analysis_id", "documents", ["analysis_id"])
    op.drop_constraint("ck_documents_source_type", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_source_type", "documents", _in("source_type", ("pdf", "text", "html", "url"))
    )

    op.create_table(
        "rule_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="SET NULL"),
        ),
        sa.Column("query", postgresql.JSONB(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="pendente"),
        sa.Column("error", sa.Text()),
        sa.Column("match_count", sa.Integer()),
        sa.Column(
            "matched_rows", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"
        ),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("verdict", sa.Text()),
        sa.Column("verdict_details", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(_in("origin", ("ia", "manual")), name="ck_rule_queries_origin"),
        sa.CheckConstraint(_in("state", ("pendente", "ok", "erro")), name="ck_rule_queries_state"),
        sa.CheckConstraint(
            f"verdict IS NULL OR {_in('verdict', ('segue', 'viola'))}",
            name="ck_rule_queries_verdict",
        ),
    )
    op.create_index("ix_rule_queries_dataset_id", "rule_queries", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("rule_queries")
    op.drop_constraint("ck_documents_source_type", "documents", type_="check")
    op.execute("DELETE FROM documents WHERE source_type NOT IN ('pdf', 'text')")
    op.create_check_constraint(
        "ck_documents_source_type", "documents", _in("source_type", ("pdf", "text"))
    )
    op.drop_index("ix_documents_analysis_id", "documents")
    op.drop_column("documents", "source_url")
    op.drop_column("documents", "analysis_id")
    op.drop_table("datasets")
    op.drop_table("analyses")
