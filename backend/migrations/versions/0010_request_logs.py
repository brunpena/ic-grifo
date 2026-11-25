"""Registro do tempo de cada requisição da API (página de desempenho).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("route_name", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("headers_ms", sa.Float(), nullable=True),
        sa.Column("db_ms", sa.Float(), server_default="0", nullable=False),
        sa.Column("db_queries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.Text(), server_default="app", nullable=False),
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("source IN ('app', 'simulacao')", name="ck_request_logs_source"),
    )
    op.create_index("ix_request_logs_route", "request_logs", ["route", "method", "created_at"])
    op.create_index("ix_request_logs_category", "request_logs", ["category", "created_at"])
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])
    op.create_index(
        "ix_request_logs_simulation",
        "request_logs",
        ["simulation_id"],
        postgresql_where=sa.text("simulation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("request_logs")
