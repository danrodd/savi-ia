"""qualify identity with erp_database (fix cruce de datos entre clientes)

Revision ID: c93e5a1d7f42
Revises: b1f4c27ae903
Create Date: 2026-09-09 11:20:00.000000

El `idUsuario` del ERP NO es único entre bases de clientes: el usuario 5
del cliente A y el 5 del cliente B son personas distintas. Sin esta
columna, el listado de conversaciones y los agregados de consumo filtran
solo por el entero y cruzan datos entre clientes.

Las columnas quedan **nullable** para las filas anteriores al multi-BD.
No se hace backfill acá: la migración no puede saber cuál es la base
default sin leer el `.env`, que es responsabilidad del seed de arranque.
El backfill lo hace `backfill_legacy_conversations` después de sembrar.

Los índices por usuario pasan a ser compuestos `(erp_database_id,
user_id)` porque esa es ahora la clave de filtrado real.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c93e5a1d7f42"
down_revision: str | None = "b1f4c27ae903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `batch_alter_table` es obligatorio para SQLite: no soporta
    # `ALTER TABLE ... ADD CONSTRAINT`, así que Alembic recrea la tabla.
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(
            sa.Column("erp_database_id", sa.Uuid(as_uuid=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_conversations_erp_database",
            "erp_databases",
            ["erp_database_id"],
            ["id"],
        )
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.create_index(
        "ix_conversations_user_id",
        "conversations",
        ["erp_database_id", "user_id"],
    )

    with op.batch_alter_table("refresh_token") as batch:
        batch.add_column(
            sa.Column("erp_database_id", sa.Uuid(as_uuid=True), nullable=True)
        )
    op.drop_index("ix_refresh_token_user_id", table_name="refresh_token")
    op.create_index(
        "ix_refresh_token_user_id",
        "refresh_token",
        ["erp_database_id", "user_id"],
    )

    # `audit_query` audita SQL ejecutado: sin la base, el registro no dice
    # contra qué cliente se ejecutó, que es la mitad del valor de auditar.
    with op.batch_alter_table("audit_query") as batch:
        batch.add_column(
            sa.Column("erp_database_id", sa.Uuid(as_uuid=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_query") as batch:
        batch.drop_column("erp_database_id")

    op.drop_index("ix_refresh_token_user_id", table_name="refresh_token")
    with op.batch_alter_table("refresh_token") as batch:
        batch.drop_column("erp_database_id")
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"])

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("fk_conversations_erp_database", type_="foreignkey")
        batch.drop_column("erp_database_id")
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
