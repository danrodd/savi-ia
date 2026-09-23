"""add pdf ai reading (lectura de PDF con IA)

Revision ID: c4d8e2f6a1b9
Revises: b3e1f9a2c7d4
Create Date: 2026-09-23 12:00:00.000000

Fase 4 del conocimiento de la empresa
(`docs/company_knowledge/04-fase-lectura-pdf-con-ia.md`):

- `company_document_pages`: cada página leída, con su método (`text` o
  `ai`) y las métricas de `pypdf`. Reprocesar reutiliza las páginas y no
  vuelve a pagar; un reinicio retoma donde iba.
- `company_document_ai_reads`: un registro por pedido al proveedor, con
  tokens y costo, para el módulo de uso. No guarda contenido.
- `company_documents`: método de lectura, páginas leídas con IA y costo.
- `company_knowledge_settings`: una sola fila con el interruptor global.
- `llm_provider_configs.document_model`: modelo de lectura; `NULL` usa el
  modelo del chat.

Escrita a mano (ver `a9c1e5f7b3d2`). Cada paso verifica lo que ya existe
porque una BD SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d8e2f6a1b9"
down_revision: str | None = "b3e1f9a2c7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "company_document_pages" not in tables:
        op.create_table(
            "company_document_pages",
            sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("method", sa.String(length=8), nullable=False),
            sa.Column("page_type", sa.String(length=16), nullable=True),
            sa.Column("legible", sa.Boolean(), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("pypdf_chars", sa.Integer(), server_default="0", nullable=False),
            sa.Column("image_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("max_image_pixels", sa.Integer(), server_default="0", nullable=False),
            sa.Column("ai_error", sa.String(length=48), nullable=True),
            sa.Column("prompt_version", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["document_id"], ["company_documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("document_id", "version", "page_number"),
        )

    if "company_document_ai_reads" not in tables:
        op.create_table(
            "company_document_ai_reads",
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            # Sin FK a propósito: el registro de gasto sobrevive a la baja
            # del documento, igual que el uso del chat sobrevive a borrar
            # una conversación.
            sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("page_from", sa.Integer(), nullable=False),
            sa.Column("page_to", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False),
            sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
            sa.Column("outcome", sa.String(length=16), nullable=False),
            sa.Column("uploaded_by_login", sa.String(length=50), nullable=False),
            sa.Column("uploaded_by_database_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_company_document_ai_reads_created_at",
            "company_document_ai_reads",
            ["created_at", "provider"],
        )
        op.create_index(
            "ix_company_document_ai_reads_document",
            "company_document_ai_reads",
            ["document_id", "version"],
        )

    if "company_knowledge_settings" not in tables:
        op.create_table(
            "company_knowledge_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ai_reading_enabled", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("updated_by_login", sa.String(length=50), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    document_columns = _columns("company_documents")
    if document_columns:
        with op.batch_alter_table("company_documents") as batch:
            if "reading_method" not in document_columns:
                batch.add_column(sa.Column("reading_method", sa.String(length=8), nullable=True))
            if "ai_page_count" not in document_columns:
                batch.add_column(
                    sa.Column("ai_page_count", sa.Integer(), server_default="0", nullable=False)
                )
            if "ai_cost_usd" not in document_columns:
                batch.add_column(sa.Column("ai_cost_usd", sa.Numeric(12, 6), nullable=True))

    provider_columns = _columns("llm_provider_configs")
    if provider_columns and "document_model" not in provider_columns:
        with op.batch_alter_table("llm_provider_configs") as batch:
            batch.add_column(sa.Column("document_model", sa.String(length=120), nullable=True))


def downgrade() -> None:
    provider_columns = _columns("llm_provider_configs")
    if "document_model" in provider_columns:
        with op.batch_alter_table("llm_provider_configs") as batch:
            batch.drop_column("document_model")

    document_columns = _columns("company_documents")
    to_drop = [
        name
        for name in ("reading_method", "ai_page_count", "ai_cost_usd")
        if name in document_columns
    ]
    if to_drop:
        with op.batch_alter_table("company_documents") as batch:
            for name in to_drop:
                batch.drop_column(name)

    tables = _tables()
    if "company_knowledge_settings" in tables:
        op.drop_table("company_knowledge_settings")
    if "company_document_ai_reads" in tables:
        op.drop_index(
            "ix_company_document_ai_reads_document", table_name="company_document_ai_reads"
        )
        op.drop_index(
            "ix_company_document_ai_reads_created_at", table_name="company_document_ai_reads"
        )
        op.drop_table("company_document_ai_reads")
    if "company_document_pages" in tables:
        op.drop_table("company_document_pages")
