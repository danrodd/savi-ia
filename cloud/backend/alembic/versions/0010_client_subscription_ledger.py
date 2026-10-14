"""suscripción por cliente y libro de movimientos

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-14

- `clients.subscription`: JSON con plan, cuota, cupo de personas y vigencia. `NULL` = sin plan.
- `client_ledger`: pagos y ajustes que registra el staff (Cloud no cobra).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("subscription", sa.JSON(), nullable=True))
    op.create_table(
        "client_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("extends_until", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind in ('payment', 'adjustment')", name="ck_client_ledger_kind_valid"),
    )
    op.create_index("ix_client_ledger_client_id", "client_ledger", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_client_ledger_client_id", table_name="client_ledger")
    op.drop_table("client_ledger")
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("subscription")
