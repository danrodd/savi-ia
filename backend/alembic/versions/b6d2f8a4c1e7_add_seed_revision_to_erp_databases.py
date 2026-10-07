"""add seed_revision to erp_databases

Revision ID: b6d2f8a4c1e7
Revises: a5c9e3b7d1f4
Create Date: 2026-10-06 10:00:00.000000

`erp_databases.seed_revision`: la revisión de `ERP_SEED_REVISION` (`.env`)
con la que se sembró o se actualizó por última vez la base default. Permite
que "Volver a configurar" del instalador cambie el ERP de una instalación ya
arrancada sin pisar, en cada inicio, lo que el administrador editó a mano.
`NULL` = fila anterior a esta columna o creada desde la aplicación.

Escrita a mano (ver `a9c1e5f7b3d2`): verifica lo que ya existe porque una
BD SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6d2f8a4c1e7"
down_revision: str | None = "a5c9e3b7d1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "erp_databases"
_COLUMN = "seed_revision"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if columns and _COLUMN not in columns:
        # Batch: SQLite no soporta todos los ALTER; en Postgres es un
        # `ALTER TABLE ADD COLUMN` común.
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(sa.Column(_COLUMN, sa.String(length=64), nullable=True))


def downgrade() -> None:
    if _COLUMN in _columns():
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
