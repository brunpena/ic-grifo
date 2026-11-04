"""Consultas SQL preparadas, executadas quando a regra é selecionada.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rule_queries", sa.Column("sql", sa.Text(), nullable=True))
    op.add_column("rule_queries", sa.Column("sql_parameters", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("rule_queries", "sql_parameters")
    op.drop_column("rule_queries", "sql")
