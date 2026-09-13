"""split conversation owner from queried database

Revision ID: d1a4c8f0e921
Revises: c93e5a1d7f42
Create Date: 2026-09-13 17:00:00.000000

`conversations.erp_database_id` cumplía dos roles que chocan: la base
que se CONSULTA (fijada al crear, D2) y la base de IDENTIDAD del dueño
(usada para filtrar "mis conversaciones" y el ownership del chat, D10).

Mientras una instalación atendía un solo cliente los dos roles
coincidían y el bug quedaba oculto. Con D10 (conversaciones de clientes
distintos en simultáneo) dejan de coincidir: un admin que abre una
conversación contra el cliente B, logueado con su identidad del cliente
A, queda con `erp_database_id = B`. Los filtros de dueño (`list_for_user`,
el ownership check de `chat`/`get`/`rename`/`delete`, y "mi consumo")
comparan esa misma columna contra la identidad del token — que es A — y
la conversación desaparece: 404 al abrirla, ausente del listado, y sin
poder mandar turnos.

Esta migración separa las dos cosas:
- `erp_database_id` sigue siendo la base CONSULTADA (sin cambios).
- `owner_erp_database_id` (nueva) es la base de IDENTIDAD del dueño.

Backfill en la propia migración (no en el seed de arranque, a
diferencia de `c93e5a1d7f42`): no depende de `.env` ni de la base
default, es una copia de una columna que ya existe en la fila. Antes de
esta migración los dos roles eran siempre la misma base, así que copiar
es exactamente correcto — no una aproximación.

Las filas verdaderamente legadas (anteriores al multi-BD, con
`erp_database_id IS NULL`) quedan también con `owner_erp_database_id
IS NULL`: las sigue resolviendo `backfill_legacy_rows` al arrancar,
extendido para llenar ambas columnas a la vez.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1a4c8f0e921"
down_revision: str | None = "c93e5a1d7f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(
            sa.Column("owner_erp_database_id", sa.Uuid(as_uuid=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_conversations_owner_erp_database",
            "erp_databases",
            ["owner_erp_database_id"],
            ["id"],
        )

    conversations = sa.table(
        "conversations",
        sa.column("erp_database_id", sa.Uuid(as_uuid=True)),
        sa.column("owner_erp_database_id", sa.Uuid(as_uuid=True)),
    )
    op.execute(
        conversations.update()
        .where(conversations.c.erp_database_id.isnot(None))
        .values(owner_erp_database_id=conversations.c.erp_database_id)
    )

    # Índice compuesto real de filtrado por dueño. El viejo
    # `ix_conversations_user_id` sobre `(erp_database_id, user_id)` se
    # conserva: `erp_database_id` sigue siendo la base consultada y el
    # ranking de consumo por cliente (`usage.per_user`) sigue agrupando
    # por ella.
    op.create_index(
        "ix_conversations_owner",
        "conversations",
        ["owner_erp_database_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_owner", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint(
            "fk_conversations_owner_erp_database", type_="foreignkey"
        )
        batch.drop_column("owner_erp_database_id")
