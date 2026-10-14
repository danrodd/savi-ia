"""add user_totp: segundo factor (TOTP) de los usuarios de SAVI

Revision ID: f1a6c3d8e2b4
Revises: e5b9c2a7d314
Create Date: 2026-10-14 16:00:00.000000

Una fila por usuario con segundo factor. `enabled_at` NULL = configuración pendiente (se
mostró el QR pero no se confirmó un código). El secreto se guarda cifrado con la misma clave
que las contraseñas de las bases del ERP.

Escrita a mano y portable (Postgres + SQLite). Verifica si la tabla ya existe porque una BD
SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a6c3d8e2b4"
down_revision: str | None = "e5b9c2a7d314"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "user_totp" in _tables():
        return
    op.create_table(
        "user_totp",
        sa.Column("erp_database_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_login", sa.String(length=50), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("erp_database_id", "user_id", name="pk_user_totp"),
    )
    op.create_index("ix_user_totp_login", "user_totp", ["erp_database_id", "user_login"])


def downgrade() -> None:
    if "user_totp" not in _tables():
        return
    op.drop_index("ix_user_totp_login", table_name="user_totp")
    op.drop_table("user_totp")
