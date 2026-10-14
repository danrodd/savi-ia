"""heartbeats, lotes de ingest y tablas de eventos tipadas

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

Las columnas de `instances` que pide §7.2 (secret_hash, previous_secret_*, fingerprint,
status, status_reason, last_seen_at, last_heartbeat, clock_skew_seconds, version, commit)
ya existen desde 0001; aquí solo se agrega el índice del secreto anterior.

PENDIENTE (E4): particionado por mes y retención (eventos 13 meses, ingest_batches 7 días,
heartbeats 30 días). Las tablas son planas por ahora; las PK de idempotencia ya están.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_TABLES = (
    "ev_turns",
    "ev_conversations",
    "ev_sessions",
    "ev_free_queries",
    "instance_databases",
)


def _event_index(table: str) -> None:
    op.create_index(
        op.f(f"ix_{table}_client_id_occurred_at"), table, ["client_id", "occurred_at"]
    )


def upgrade() -> None:
    op.create_index(
        op.f("ix_instances_previous_secret_hash"), "instances", ["previous_secret_hash"]
    )

    op.create_table(
        "heartbeats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeats")),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["instances.id"],
            name=op.f("fk_heartbeats_instance_id_instances"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_heartbeats_instance_id_received_at"),
        "heartbeats",
        ["instance_id", "received_at"],
    )

    op.create_table(
        "ingest_batches",
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("rejected", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("instance_id", "batch_id", name=op.f("pk_ingest_batches")),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["instances.id"],
            name=op.f("fk_ingest_batches_instance_id_instances"),
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "ev_turns",
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_ref", sa.Uuid(), nullable=False),
        sa.Column("database_ref", sa.Uuid(), nullable=True),
        sa.Column("user_ref", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("finish_reason", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_creation_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("tools", postgresql.JSONB(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(16), nullable=True),
        sa.PrimaryKeyConstraint("instance_id", "source_id", name=op.f("pk_ev_turns")),
    )

    op.create_table(
        "ev_conversations",
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_ref", sa.Uuid(), nullable=False),
        sa.Column("database_ref", sa.Uuid(), nullable=True),
        sa.Column("user_ref", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("instance_id", "source_id", name=op.f("pk_ev_conversations")),
    )

    op.create_table(
        "ev_sessions",
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_ref", sa.String(32), nullable=False),
        sa.Column("database_ref", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("instance_id", "source_id", name=op.f("pk_ev_sessions")),
    )

    op.create_table(
        "ev_free_queries",
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_ref", sa.Uuid(), nullable=True),
        sa.Column("database_ref", sa.Uuid(), nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("estimated_rows", sa.Integer(), nullable=True),
        sa.Column("returned_rows", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("instance_id", "source_id", name=op.f("pk_ev_free_queries")),
    )

    op.create_table(
        "instance_databases",
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("database_ref", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_usable", sa.Boolean(), nullable=False),
        sa.Column("credentials_unreadable", sa.Boolean(), nullable=False),
        sa.Column("last_connection_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "instance_id", "database_ref", "snapshot_date", name=op.f("pk_instance_databases")
        ),
    )

    for table in _EVENT_TABLES:
        _event_index(table)


def downgrade() -> None:
    for table in reversed(_EVENT_TABLES):
        op.drop_index(op.f(f"ix_{table}_client_id_occurred_at"), table_name=table)
        op.drop_table(table)
    op.drop_table("ingest_batches")
    op.drop_index(op.f("ix_heartbeats_instance_id_received_at"), table_name="heartbeats")
    op.drop_table("heartbeats")
    op.drop_index(op.f("ix_instances_previous_secret_hash"), table_name="instances")
