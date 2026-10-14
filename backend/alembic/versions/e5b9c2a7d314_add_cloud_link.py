"""add cloud_link, cloud_sync_watermarks e indices keyset para SAVI Cloud

Revision ID: e5b9c2a7d314
Revises: c3a7d1e9f5b2
Create Date: 2026-10-14 10:00:00.000000

`cloud_link` es una sola fila (`CHECK id = 1`) con el estado de la vinculación
con SAVI Cloud; `cloud_sync_watermarks` guarda la marca de agua de cada stream.

Los cuatro indices `(created_at, id)` los necesita el extractor incremental:
sin ellos cada lote es un `SCAN` + `TEMP B-TREE FOR ORDER BY` sobre la tabla
entera (verificado con `EXPLAIN QUERY PLAN` en SQLite; con el indice pasa a
`SEARCH ... USING INDEX`).

Escrita a mano y portable (Postgres + SQLite). Verifica si cada objeto ya
existe porque una BD SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5b9c2a7d314"
down_revision: str | None = "c3a7d1e9f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: tuple[tuple[str, str, tuple[str, str]], ...] = (
    ("ix_messages_created_at_id", "messages", ("created_at", "id")),
    ("ix_conversations_created_at_id", "conversations", ("created_at", "id")),
    ("ix_refresh_token_created_at_jti", "refresh_token", ("created_at", "jti")),
    ("ix_audit_query_created_at_id", "audit_query", ("created_at", "id")),
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    return {str(ix["name"]) for ix in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _tables()
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    if "cloud_link" not in tables:
        op.create_table(
            "cloud_link",
            sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("cloud_url", sa.String(length=255), nullable=False),
            sa.Column("instance_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("client_code", sa.String(length=32), nullable=True),
            sa.Column("client_name", sa.String(length=200), nullable=True),
            sa.Column("secret_encrypted", sa.Text(), nullable=True),
            sa.Column("pseudonym_key_encrypted", sa.Text(), nullable=False),
            sa.Column("install_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("policy", json_type, nullable=True),
            sa.Column("notices", json_type, nullable=False),
            sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_heartbeat_ok_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_code", sa.String(length=64), nullable=True),
            sa.Column("consecutive_failures", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("id = 1", name="ck_cloud_link_singleton"),
        )

    if "cloud_sync_watermarks" not in tables:
        op.create_table(
            "cloud_sync_watermarks",
            sa.Column("stream", sa.String(length=32), nullable=False),
            sa.Column("watermark_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("watermark_id", sa.String(length=64), nullable=False),
            sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("stream"),
        )

    for name, table, columns in _INDEXES:
        if table in tables and name not in _index_names(table):
            op.create_index(name, table, list(columns))


def downgrade() -> None:
    tables = _tables()
    for name, table, _ in reversed(_INDEXES):
        if table in tables and name in _index_names(table):
            op.drop_index(name, table_name=table)
    if "cloud_sync_watermarks" in tables:
        op.drop_table("cloud_sync_watermarks")
    if "cloud_link" in tables:
        op.drop_table("cloud_link")
