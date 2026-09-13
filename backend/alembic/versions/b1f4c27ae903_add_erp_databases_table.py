"""add erp_databases table (multi-BD del ERP)

Revision ID: b1f4c27ae903
Revises: 4a8dcb6945b3
Create Date: 2026-09-09 10:40:00.000000

Registro de las conexiones a las BD de los clientes del ERP. Vive en la
BD del agente porque es configuración de SAVI, no dato de un cliente.

Escrita a mano y no autogenerada: el `.env` de desarrollo apunta a
SQLite, y un autogenerate contra una BD vacía produciría un create_all
de todas las tablas en vez del delta.

Los tres únicos son PARCIALES (`WHERE deleted_at IS NULL`) para que una
base eliminada no bloquee registrar otra con el mismo código o nombre.
SQLite soporta índices parciales; se declaran con `sqlite_where` +
`postgresql_where` para que el DDL salga bien en los dos motores.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1f4c27ae903"
down_revision: str | None = "4a8dcb6945b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "erp_databases",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "statement_timeout_ms",
            sa.Integer(),
            server_default="60000",
            nullable=False,
        ),
        sa.Column(
            "is_default", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "credentials_unreadable",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("last_connection_ok_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_erp_databases_code",
        "erp_databases",
        ["code"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_erp_databases_name",
        "erp_databases",
        ["name"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_erp_databases_default",
        "erp_databases",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL AND is_default"),
        postgresql_where=sa.text("deleted_at IS NULL AND is_default"),
    )
    op.create_index(
        "ix_erp_databases_active",
        "erp_databases",
        ["deleted_at", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_erp_databases_active", table_name="erp_databases")
    op.drop_index("uq_erp_databases_default", table_name="erp_databases")
    op.drop_index("uq_erp_databases_name", table_name="erp_databases")
    op.drop_index("uq_erp_databases_code", table_name="erp_databases")
    op.drop_table("erp_databases")
