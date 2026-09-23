"""add ai reading consent (consentimiento para leer PDF con IA)

Revision ID: d7a3f1c9e2b5
Revises: c4d8e2f6a1b9
Create Date: 2026-09-23 18:00:00.000000

La lectura con IA manda los PDF completos al proveedor. Pasa de venir
activada a necesitar que un administrador acepte el envío a un proveedor
concreto (`ai_reading_consent_provider`), y queda registrado quién y cuándo.
Si cambia el proveedor activo, la lectura se pausa hasta aceptar el nuevo.

Las instalaciones existentes quedan sin consentimiento: nadie aceptó
explícitamente, así que no se manda nada hasta que un administrador lo haga.

Escrita a mano (ver `a9c1e5f7b3d2`). Cada paso verifica lo que ya existe
porque una BD SQLite nueva nace del metadata y se sella en `head`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7a3f1c9e2b5"
down_revision: str | None = "c4d8e2f6a1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "company_knowledge_settings"
_CONSENT_COLUMNS = (
    "ai_reading_consent_provider",
    "ai_reading_consent_by_login",
    "ai_reading_consent_at",
)


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return
    with op.batch_alter_table(_TABLE) as batch:
        if "ai_reading_consent_provider" not in columns:
            batch.add_column(
                sa.Column("ai_reading_consent_provider", sa.String(length=32), nullable=True)
            )
        if "ai_reading_consent_by_login" not in columns:
            batch.add_column(
                sa.Column("ai_reading_consent_by_login", sa.String(length=50), nullable=True)
            )
        if "ai_reading_consent_at" not in columns:
            batch.add_column(
                sa.Column("ai_reading_consent_at", sa.DateTime(timezone=True), nullable=True)
            )
        batch.alter_column("ai_reading_enabled", existing_type=sa.Boolean(), server_default="false")


def downgrade() -> None:
    columns = _columns()
    if not columns:
        return
    with op.batch_alter_table(_TABLE) as batch:
        for name in _CONSENT_COLUMNS:
            if name in columns:
                batch.drop_column(name)
        batch.alter_column("ai_reading_enabled", existing_type=sa.Boolean(), server_default="true")
