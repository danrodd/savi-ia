"""clients, instances y enrollment_tokens

Revision ID: 0001
Revises:
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("nit", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        sa.UniqueConstraint("code", name=op.f("uq_clients_code")),
        sa.CheckConstraint("status in ('active', 'suspended')", name=op.f("ck_clients_status_valid")),
        sa.CheckConstraint("length(code) between 2 and 32", name=op.f("ck_clients_code_length")),
    )

    op.create_table(
        "instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("deployment_mode", sa.String(32), nullable=False),
        sa.Column("os", sa.String(200), nullable=False),
        sa.Column("agent_db_engine", sa.String(32), nullable=False),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("commit", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("status_reason", sa.String(64), nullable=True),
        sa.Column("secret_hash", sa.LargeBinary(), nullable=False),
        sa.Column("previous_secret_hash", sa.LargeBinary(), nullable=True),
        sa.Column("previous_secret_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", postgresql.JSONB(), nullable=True),
        sa.Column("clock_skew_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instances")),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name=op.f("fk_instances_client_id_clients"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("secret_hash", name=op.f("uq_instances_secret_hash")),
        sa.CheckConstraint(
            "status in ('active', 'suspended', 'revoked')",
            name=op.f("ck_instances_status_valid"),
        ),
    )
    op.create_index(op.f("ix_instances_client_id"), "instances", ["client_id"])

    op.create_table(
        "enrollment_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_instance_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_tokens")),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name=op.f("fk_enrollment_tokens_client_id_clients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["used_by_instance_id"],
            ["instances.id"],
            name=op.f("fk_enrollment_tokens_used_by_instance_id_instances"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_enrollment_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_enrollment_tokens_client_id"), "enrollment_tokens", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_enrollment_tokens_client_id"), table_name="enrollment_tokens")
    op.drop_table("enrollment_tokens")
    op.drop_index(op.f("ix_instances_client_id"), table_name="instances")
    op.drop_table("instances")
    op.drop_table("clients")
