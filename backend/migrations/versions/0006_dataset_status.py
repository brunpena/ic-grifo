"""Bases lidas em segundo plano (status) e sem linhas de amostra no banco.

As linhas da base ficam só no arquivo do storage, lidas pelas buscas das regras.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # As bases já existentes foram lidas no envio: entram como prontas.
    op.add_column(
        "datasets", sa.Column("status", sa.Text(), nullable=False, server_default="ready")
    )
    op.alter_column("datasets", "status", server_default=None)
    op.add_column("datasets", sa.Column("status_message", sa.Text()))
    op.create_check_constraint(
        "ck_datasets_status", "datasets", "status IN ('processing', 'ready', 'error')"
    )
    op.drop_column("datasets", "sample_rows")


def downgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("sample_rows", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.alter_column("datasets", "sample_rows", server_default=None)
    op.drop_constraint("ck_datasets_status", "datasets", type_="check")
    op.drop_column("datasets", "status_message")
    op.drop_column("datasets", "status")
