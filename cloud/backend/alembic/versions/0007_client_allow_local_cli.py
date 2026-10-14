"""política por cliente: permitir el CLI de Claude local

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14

- `clients.allow_local_cli`: las instalaciones locales del cliente pueden ofrecer el CLI de
  Claude con la cuenta de la persona. Apagado por defecto: lo decide SEO Group.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(
            sa.Column(
                "allow_local_cli", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("allow_local_cli")
