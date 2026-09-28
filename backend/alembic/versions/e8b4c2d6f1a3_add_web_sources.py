"""add web sources (importar conocimiento desde la web)

Revision ID: e8b4c2d6f1a3
Revises: d7a3f1c9e2b5
Create Date: 2026-09-28 10:00:00.000000

Fase 5 del conocimiento de la empresa
(`docs/company_knowledge/05-fase-importar-desde-web.md`):

- `company_web_sources`: una página o un sitio que SAVI lee y refresca,
  con los mismos permisos que un documento.
- `company_web_source_databases`: su alcance por base.
- `company_web_pages`: cada página, el documento que la representa y cómo
  saber si cambió (`etag`, `last_modified`, hash del texto).
- `company_documents.source_kind` y `source_url`: una página importada es
  un documento más; se cita con su URL y no aparece en la tabla de
  documentos subidos.

Escrita a mano (ver `a9c1e5f7b3d2`). Cada paso verifica lo que ya existe
porque una BD SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8b4c2d6f1a3"
down_revision: str | None = "d7a3f1c9e2b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    tables = _tables()

    if "company_web_sources" not in tables:
        op.create_table(
            "company_web_sources",
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("url", sa.String(length=2048), nullable=False),
            sa.Column("mode", sa.String(length=8), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("refresh", sa.String(length=8), nullable=False),
            sa.Column("max_pages", sa.Integer(), nullable=False),
            sa.Column("excluded_sections", sa.JSON(), server_default="[]", nullable=False),
            sa.Column("visibility", sa.String(length=16), nullable=False),
            sa.Column("modules", sa.JSON(), server_default="[]", nullable=False),
            sa.Column("all_databases", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("status_code", sa.String(length=32), nullable=True),
            sa.Column("status_message", sa.String(length=500), nullable=True),
            sa.Column("page_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_crawl_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_crawl_finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_login", sa.String(length=50), nullable=False),
            sa.Column("created_by_database_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
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
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by_database_id"], ["erp_databases.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_company_web_sources_status", "company_web_sources", ["status", "created_at"]
        )

    if "company_web_source_databases" not in tables:
        op.create_table(
            "company_web_source_databases",
            sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("erp_database_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["source_id"], ["company_web_sources.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["erp_database_id"], ["erp_databases.id"]),
            sa.PrimaryKeyConstraint("source_id", "erp_database_id"),
        )

    if "company_web_pages" not in tables:
        op.create_table(
            "company_web_pages",
            sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("url", sa.String(length=2048), nullable=False),
            sa.Column("title", sa.String(length=200), server_default="", nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("status_detail", sa.String(length=300), nullable=True),
            sa.Column("etag", sa.String(length=300), nullable=True),
            sa.Column("last_modified", sa.String(length=100), nullable=True),
            sa.Column("content_hash", sa.String(length=64), server_default="", nullable=False),
            sa.Column("missing_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["company_documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_id"], ["company_web_sources.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("document_id"),
        )
        op.create_index(
            "ix_company_web_pages_source",
            "company_web_pages",
            ["source_id", "url"],
            unique=True,
        )

    document_columns = _columns("company_documents")
    if document_columns:
        with op.batch_alter_table("company_documents") as batch:
            if "source_kind" not in document_columns:
                batch.add_column(
                    sa.Column(
                        "source_kind", sa.String(length=8), server_default="upload", nullable=False
                    )
                )
            if "source_url" not in document_columns:
                batch.add_column(sa.Column("source_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    document_columns = _columns("company_documents")
    to_drop = [name for name in ("source_kind", "source_url") if name in document_columns]
    if to_drop:
        with op.batch_alter_table("company_documents") as batch:
            for name in to_drop:
                batch.drop_column(name)
    tables = _tables()
    if "company_web_pages" in tables:
        op.drop_index("ix_company_web_pages_source", table_name="company_web_pages")
        op.drop_table("company_web_pages")
    if "company_web_source_databases" in tables:
        op.drop_table("company_web_source_databases")
    if "company_web_sources" in tables:
        op.drop_index("ix_company_web_sources_status", table_name="company_web_sources")
        op.drop_table("company_web_sources")
