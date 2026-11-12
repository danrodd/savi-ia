"""add result_sets table and data_tables to messages

Revision ID: e5f9b3d7c1a2
Revises: d4e8a2c6b0f1

El resultado completo de cada consulta al ERP se guarda en el servidor: el chat
muestra una vista previa y Exportar entrega todo en Excel, PDF o CSV (ver
`docs/plataforma/11-resultados-completos.md`). `messages.data_tables` guarda qué
conjuntos acompañan a cada respuesta, para mostrarlos al recargar.

Portable (Postgres + SQLite): JSON genérico, sin `now()`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f9b3d7c1a2"
down_revision: str | None = "d4e8a2c6b0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "result_sets"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("columns", sa.JSON(), nullable=False),
            sa.Column("rows", sa.JSON(), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=False),
            sa.Column("total_is_lower_bound", sa.Boolean(), nullable=False),
            sa.Column("has_personal_data", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_result_sets_conversation_created", _TABLE, ["conversation_id", "created_at"]
        )
    if "messages" in tables:
        columns = {c["name"] for c in inspector.get_columns("messages")}
        if "data_tables" not in columns:
            op.add_column("messages", sa.Column("data_tables", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "messages" in tables:
        columns = {c["name"] for c in inspector.get_columns("messages")}
        if "data_tables" in columns:
            op.drop_column("messages", "data_tables")
    if _TABLE in tables:
        op.drop_index("ix_result_sets_conversation_created", table_name=_TABLE)
        op.drop_table(_TABLE)
