"""add chat attachments (imágenes adjuntas a los mensajes)

Revision ID: a5c9e3b7d1f4
Revises: f4b8d2e6a9c1
Create Date: 2026-10-06 10:00:00.000000

- `chat_attachments`: metadata de cada imagen (dueño, mensaje, tipo, nombre,
  peso y dimensiones). `message_id` es NULL entre la subida y el envío.
- `chat_attachment_blobs`: los bytes, en tabla aparte para que listar
  mensajes nunca los cargue (mismo patrón que `company_document_blobs`).

Escrita a mano (ver `a9c1e5f7b3d2`): portable a PostgreSQL y SQLite, y cada
paso verifica lo que ya existe porque una BD SQLite nueva nace del metadata y
se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5c9e3b7d1f4"
down_revision: str | None = "f4b8d2e6a9c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "chat_attachments" not in tables:
        op.create_table(
            "chat_attachments",
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("owner_erp_database_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("mime", sa.String(length=32), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["owner_erp_database_id"], ["erp_databases.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_chat_attachments_message", "chat_attachments", ["message_id"])
        op.create_index(
            "ix_chat_attachments_owner_created",
            "chat_attachments",
            ["user_id", "created_at"],
        )

    if "chat_attachment_blobs" not in tables:
        op.create_table(
            "chat_attachment_blobs",
            sa.Column("attachment_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.ForeignKeyConstraint(["attachment_id"], ["chat_attachments.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("attachment_id"),
        )


def downgrade() -> None:
    tables = _tables()
    if "chat_attachment_blobs" in tables:
        op.drop_table("chat_attachment_blobs")
    if "chat_attachments" in tables:
        op.drop_index("ix_chat_attachments_owner_created", table_name="chat_attachments")
        op.drop_index("ix_chat_attachments_message", table_name="chat_attachments")
        op.drop_table("chat_attachments")
