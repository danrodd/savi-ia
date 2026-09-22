"""add index for provider usage queries

Revision ID: b3e1f9a2c7d4
Revises: a9c1e5f7b3d2
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3e1f9a2c7d4"
down_revision: str | None = "a9c1e5f7b3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_messages_role_created_at_provider"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes("messages")}
    if _INDEX_NAME in existing:
        return
    # Compuesto simple, NO parcial: `agent_db` también corre en SQLite
    # para la instalación de escritorio, donde `postgresql_where` se
    # ignora en silencio. Cubre el predicado común de todo el módulo
    # `usage`: turnos del asistente en un rango de fecha, filtrados por
    # proveedor.
    op.create_index(
        _INDEX_NAME,
        "messages",
        ["role", "created_at", "provider"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes("messages")}
    if _INDEX_NAME in existing:
        op.drop_index(_INDEX_NAME, table_name="messages")
