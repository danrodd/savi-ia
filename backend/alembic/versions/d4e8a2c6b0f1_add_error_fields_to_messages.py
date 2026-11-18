"""add error fields to messages (turnos fallidos)

Revision ID: d4e8a2c6b0f1
Revises: c3a7d1e9f5b2

Un turno que terminaba en error antes del primer texto no se guardaba: al
recargar, la pregunta quedaba sin respuesta y soporte no tenía qué mirar.
Ahora se guarda con su categoría, el texto que vio el usuario y un código de
soporte que también queda en el log.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e8a2c6b0f1"
down_revision: str | None = "c3a7d1e9f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("error_code", sa.String(length=32)),
    ("error_message", sa.Text()),
    ("support_code", sa.String(length=16)),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("messages")}
    for name, type_ in _COLUMNS:
        if name not in existing:
            op.add_column("messages", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("messages")}
    for name, _ in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("messages", name)
