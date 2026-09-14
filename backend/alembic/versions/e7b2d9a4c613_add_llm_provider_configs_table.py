"""add llm_provider_configs table (proveedores de IA configurables)

Revision ID: e7b2d9a4c613
Revises: d1a4c8f0e921
Create Date: 2026-09-13 18:00:00.000000

Configuración de los proveedores de IA: una fila por proveedor, con la
credencial cifrada y un único activo (índice único parcial sobre
`is_active`). Escrita a mano por el mismo motivo que `b1f4c27ae903`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b2d9a4c613"
down_revision: str | None = "d1a4c8f0e921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_configs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("credential_kind", sa.String(length=32), nullable=False),
        sa.Column("credential_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "credentials_unreadable",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("chat_model", sa.String(length=120), nullable=False),
        sa.Column("title_model", sa.String(length=120), nullable=False),
        sa.Column(
            "pricing",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_test_ok_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("provider"),
    )
    op.create_index(
        "uq_llm_provider_configs_active",
        "llm_provider_configs",
        ["is_active"],
        unique=True,
        sqlite_where=sa.text("is_active"),
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_llm_provider_configs_active", table_name="llm_provider_configs")
    op.drop_table("llm_provider_configs")
