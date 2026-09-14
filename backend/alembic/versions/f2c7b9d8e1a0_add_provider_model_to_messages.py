"""add provider and model metadata to messages

Revision ID: f2c7b9d8e1a0
Revises: e7b2d9a4c613
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2c7b9d8e1a0"
down_revision: str | None = "e7b2d9a4c613"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "provider" not in columns:
        op.add_column("messages", sa.Column("provider", sa.String(length=32), nullable=True))
    if "model" not in columns:
        op.add_column("messages", sa.Column("model", sa.String(length=120), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "model" in columns:
        op.drop_column("messages", "model")
    if "provider" in columns:
        op.drop_column("messages", "provider")
