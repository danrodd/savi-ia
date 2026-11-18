"""add generated_files table and files to messages

Revision ID: f6a1c4e8d2b3
Revises: e5f9b3d7c1a2

Archivos que SAVI genera para una respuesta (exportaciones y documentos en
Excel, PDF, CSV o Word; ver `docs/plataforma/12-generacion-de-documentos.md`).
`messages.files` guarda cuáles acompañan a cada respuesta, para mostrarlos al
recargar. Portable (Postgres + SQLite).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a1c4e8d2b3"
down_revision: str | None = "e5f9b3d7c1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "generated_files"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("filename", sa.String(length=160), nullable=False),
            sa.Column("media_type", sa.String(length=120), nullable=False),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.Column("has_personal_data", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_generated_files_conversation_created", _TABLE, ["conversation_id", "created_at"]
        )
    if "messages" in tables:
        columns = {c["name"] for c in inspector.get_columns("messages")}
        if "files" not in columns:
            op.add_column("messages", sa.Column("files", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "messages" in tables:
        columns = {c["name"] for c in inspector.get_columns("messages")}
        if "files" in columns:
            op.drop_column("messages", "files")
    if _TABLE in tables:
        op.drop_index("ix_generated_files_conversation_created", table_name=_TABLE)
        op.drop_table(_TABLE)
