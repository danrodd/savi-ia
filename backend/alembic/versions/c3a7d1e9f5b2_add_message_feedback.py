"""add message_feedback table (calificación 👍/👎 por respuesta)

Revision ID: c3a7d1e9f5b2
Revises: b6d2f8a4c1e7
Create Date: 2026-10-13 09:00:00.000000

Una fila por (mensaje, usuario): rating `up`/`down`, motivo opcional (solo con
`down`) y comentario libre. La identidad del autor es el par
`(user_id, owner_erp_database_id)`: el `idUsuario` del ERP se repite entre
clientes. `user_login`/`user_name` se guardan al calificar para que el panel
del administrador no tenga que consultar el ERP de cada cliente.

Escrita a mano y portable (Postgres + SQLite): sin `now()`, sin `JSONB`; las
fechas las pone la aplicación. Verifica si la tabla ya existe porque una BD
SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3a7d1e9f5b2"
down_revision: str | None = "b6d2f8a4c1e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "message_feedback"


def _exists() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _exists():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("owner_erp_database_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("user_login", sa.String(length=50), nullable=True),
        sa.Column("user_name", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_erp_database_id"], ["erp_databases.id"]),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_feedback_message_user"),
        sa.CheckConstraint("rating IN ('up', 'down')", name="ck_message_feedback_rating"),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN "
            "('dato_incorrecto', 'no_entendio', 'incompleta', 'muy_lenta', 'otra')",
            name="ck_message_feedback_reason",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR rating = 'down'", name="ck_message_feedback_reason_requires_down"
        ),
        sa.CheckConstraint(
            "comment IS NULL OR length(comment) <= 1000",
            name="ck_message_feedback_comment_length",
        ),
    )
    op.create_index(
        "ix_message_feedback_owner_created", _TABLE, ["owner_erp_database_id", "created_at"]
    )
    op.create_index("ix_message_feedback_message", _TABLE, ["message_id"])


def downgrade() -> None:
    if not _exists():
        return
    op.drop_index("ix_message_feedback_message", table_name=_TABLE)
    op.drop_index("ix_message_feedback_owner_created", table_name=_TABLE)
    op.drop_table(_TABLE)
