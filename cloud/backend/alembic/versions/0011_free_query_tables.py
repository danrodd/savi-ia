"""tablas del ERP por consulta libre (vacíos del catálogo)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-25

- `ev_free_queries.tables`: JSON con las tablas del ERP (`Esquema.Tabla`) que leyó cada
  consulta libre. `NULL` en los eventos de instancias que todavía no lo mandan. Sirve para
  ver entre clientes qué le falta al catálogo de datos; nunca lleva columnas ni valores.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ev_free_queries") as batch:
        batch.add_column(
            sa.Column(
                "tables",
                sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("ev_free_queries") as batch:
        batch.drop_column("tables")
