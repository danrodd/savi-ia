"""política por cliente (identidad y bloqueo de configuración) y etiquetas de persona

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14

- `clients.identity_mode`: `pseudonym` (clientes) o `named` (organización interna).
- `clients.config_locked`: las instalaciones del cliente quedan solo con el chat.
- `ev_sessions.user_label`: código de usuario, solo para clientes en modo `named`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(
            sa.Column(
                "identity_mode",
                sa.String(length=16),
                nullable=False,
                server_default="pseudonym",
            )
        )
        batch.add_column(
            sa.Column("config_locked", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.create_check_constraint(
            op.f("ck_clients_identity_mode_valid"),
            "identity_mode in ('pseudonym', 'named')",
        )
    op.add_column("ev_sessions", sa.Column("user_label", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("ev_sessions", "user_label")
    with op.batch_alter_table("clients") as batch:
        batch.drop_constraint(op.f("ck_clients_identity_mode_valid"), type_="check")
        batch.drop_column("config_locked")
        batch.drop_column("identity_mode")
