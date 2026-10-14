"""política de IA por cliente: proveedores permitidos y topes

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14

- `clients.ai_policy`: JSON con `allowed_providers`, `user_monthly_usd`,
  `provider_monthly_usd` y `user_overrides`. `NULL` = sin límites.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("ai_policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("ai_policy")
