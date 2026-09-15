"""add company_knowledge tables (documentos propios de la empresa)

Revision ID: a9c1e5f7b3d2
Revises: f2c7b9d8e1a0
Create Date: 2026-09-14 18:00:00.000000

Cuatro tablas: documento, alcance por base, blob original y fragmentos,
más `messages.sources` (fuentes citadas por respuesta).
Escrita a mano por el mismo motivo que `b1f4c27ae903` (el `.env` de
desarrollo apunta a SQLite y un autogenerate contra una BD vacía
produciría un `create_all` de todo).

El único sobre `sha256` es PARCIAL (`WHERE deleted_at IS NULL`) para que
un documento eliminado no bloquee volver a subir el mismo archivo. Se
declara con `sqlite_where` + `postgresql_where` para que el DDL salga
bien en los dos motores.

`embedding` y `content` van como `LargeBinary` (`BYTEA` en Postgres,
`BLOB` en SQLite): portable sin extensiones de base de datos.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c1e5f7b3d2"
down_revision: str | None = "f2c7b9d8e1a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("status_code", sa.String(length=48), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column(
            "modules",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "all_databases", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column("uploaded_by_login", sa.String(length=50), nullable=False),
        sa.Column("uploaded_by_database_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_database_id"], ["erp_databases.id"], name="fk_company_documents_database"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_company_documents_sha256",
        "company_documents",
        ["sha256"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_company_documents_status",
        "company_documents",
        ["status", "created_at"],
    )

    op.create_table(
        "company_document_databases",
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("erp_database_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["company_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["erp_database_id"], ["erp_databases.id"]),
        sa.PrimaryKeyConstraint("document_id", "erp_database_id"),
    )

    op.create_table(
        "company_document_blobs",
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["company_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("document_id"),
    )

    op.create_table(
        "company_document_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("heading", sa.String(length=300), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["company_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_company_document_chunks_document_ordinal",
        "company_document_chunks",
        ["document_id", "ordinal"],
    )

    # Fuentes citadas por respuesta del asistente. NULL = sin citas; sin
    # backfill: los mensajes previos no citaban documentos. Protegido como
    # `f2c7b9d8e1a0`: una BD parcial puede no tener `messages` todavía.
    inspector = sa.inspect(op.get_bind())
    if "messages" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("messages")}
        if "sources" not in columns:
            op.add_column(
                "messages",
                sa.Column(
                    "sources",
                    sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("messages")}
        if "sources" in columns:
            with op.batch_alter_table("messages") as batch:
                batch.drop_column("sources")
    op.drop_index(
        "ix_company_document_chunks_document_ordinal",
        table_name="company_document_chunks",
    )
    op.drop_table("company_document_chunks")
    op.drop_table("company_document_blobs")
    op.drop_table("company_document_databases")
    op.drop_index("ix_company_documents_status", table_name="company_documents")
    op.drop_index("uq_company_documents_sha256", table_name="company_documents")
    op.drop_table("company_documents")
