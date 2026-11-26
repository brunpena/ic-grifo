"""Conversa com a IA guardada na regra aprovada (histórico do documento).

Regras antigas ficam com a conversa vazia.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column(
            "conversation", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")
        ),
    )


def downgrade() -> None:
    op.drop_column("rules", "conversation")
