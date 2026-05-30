"""change conversations.user_id to integer (erp idUsuario)

Revision ID: 4a8dcb6945b3
Revises: 78017cfa55be
Create Date: 2026-05-28 23:05:50.633362

Postgres no puede castear UUID a Integer directamente. Como las
conversaciones existentes en agent_db son de etapa pre-auth (todos los
user_id son NULL), hacemos drop + re-add para evitar el USING explícito.
Si en el futuro hubiera data legítima en user_id antes de aplicar esta
migración, este script borraría esos owners — habría que escribir un
script de mapeo manual antes.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a8dcb6945b3"
down_revision: str | None = "78017cfa55be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")
    op.add_column(
        "conversations",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_conversations_user_id", "conversations", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")
    op.add_column(
        "conversations",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_conversations_user_id", "conversations", ["user_id"], unique=False
    )
