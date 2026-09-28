"""add upload limit to company knowledge settings

Revision ID: f4b8d2e6a9c1
Revises: e8b4c2d6f1a3
Create Date: 2026-09-28 16:00:00.000000

`company_knowledge_settings.upload_limit_per_hour`: cupo de subidas,
reemplazos y lecturas de sitios por usuario y por hora que un administrador
fija desde la pantalla de Conocimiento. `NULL` = el valor por defecto del
servidor (`RATE_LIMIT_UPLOAD_PER_HOUR`).

Escrita a mano (ver `a9c1e5f7b3d2`): verifica lo que ya existe porque una
BD SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4b8d2e6a9c1"
down_revision: str | None = "e8b4c2d6f1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "company_knowledge_settings"
_COLUMN = "upload_limit_per_hour"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if columns and _COLUMN not in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    if _COLUMN in _columns():
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
