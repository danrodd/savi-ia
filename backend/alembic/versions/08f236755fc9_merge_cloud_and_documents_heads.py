"""merge cloud and documents heads

Revision ID: 08f236755fc9
Revises: f1a6c3d8e2b4, f6a1c4e8d2b3

Une las dos ramas de migraciones: la de SAVI Cloud y el doble factor
(`f1a6c3d8e2b4`) y la de los resultados completos y los documentos generados
(`f6a1c4e8d2b3`). No cambia el esquema.
"""

from collections.abc import Sequence

revision: str = "08f236755fc9"
down_revision: str | Sequence[str] | None = ("f1a6c3d8e2b4", "f6a1c4e8d2b3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
