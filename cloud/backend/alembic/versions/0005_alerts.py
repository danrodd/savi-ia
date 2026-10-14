"""alertas y ajustes de reglas

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14

El índice único parcial `uq_alerts_dedup_key_live` impide que existan dos alertas vivas
(abierta o reconocida) con la misma clave: lo garantiza la base, no solo el motor.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_LIVE = "status in ('open', 'acknowledged')"


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("dedup_key", sa.String(length=128), nullable=False),
        sa.Column("details", _JSON, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=254), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=254), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('open', 'acknowledged', 'resolved')",
            name=op.f("ck_alerts_status_valid"),
        ),
        sa.CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name=op.f("ck_alerts_severity_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(
        "uq_alerts_dedup_key_live",
        "alerts",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text(_LIVE),
        sqlite_where=sa.text(_LIVE),
    )
    op.create_index("ix_alerts_status_opened_at", "alerts", ["status", "opened_at"])
    op.create_index("ix_alerts_client_id", "alerts", ["client_id"])

    op.create_table(
        "alert_rules",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_alert_rules")),
    )


def downgrade() -> None:
    op.drop_table("alert_rules")
    op.drop_index("ix_alerts_client_id", table_name="alerts")
    op.drop_index("ix_alerts_status_opened_at", table_name="alerts")
    op.drop_index("uq_alerts_dedup_key_live", table_name="alerts")
    op.drop_table("alerts")
