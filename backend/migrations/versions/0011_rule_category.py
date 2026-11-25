"""Regras criadas a partir de trechos grifados: categoria e interpretação.

A extração automática foi descartada: o checkpoint dela deixa de existir. Regras
antigas com busca ficam em `csv`; as demais, em `geral`.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("category", sa.Text(), nullable=False, server_default="geral"))
    op.add_column("rules", sa.Column("interpretation", sa.Text(), nullable=True))
    op.create_check_constraint("ck_rules_category", "rules", "category IN ('csv', 'geral')")
    op.execute(
        "UPDATE rules SET category = 'csv' "
        "WHERE EXISTS (SELECT 1 FROM rule_queries q WHERE q.rule_id = rules.id)"
    )
    op.drop_column("documents", "extraction_checkpoint")


def downgrade() -> None:
    op.add_column(
        "documents", sa.Column("extraction_checkpoint", postgresql.JSONB(), nullable=True)
    )
    op.drop_constraint("ck_rules_category", "rules", type_="check")
    op.drop_column("rules", "interpretation")
    op.drop_column("rules", "category")
