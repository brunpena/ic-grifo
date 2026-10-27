"""Resultados e planos da verificação de todas as regras.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("original_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("rules", sa.Column("validation", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "original_size_bytes")
    op.drop_column("rules", "validation")
