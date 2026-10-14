"""política por cliente: bases que puede consultar cada persona

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14

- `clients.access_policy`: JSON con `default_databases` y `user_databases`. `NULL` = sin
  restricción (lo que permita el ERP).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("access_policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("access_policy")
