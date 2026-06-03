"""Impl `SeoPlanRepository` contra `SEO.Modulo` del ERP.

`SEO.Modulo` puede tener múltiples filas (histórico del sync con el
portal SEO). La vigente es la de mayor `idModulo`. Si la tabla está
vacía, retornamos dict vacío y la capa de aplicación trata al cliente
como "sin plan vertical".

Las columnas son booleanas. Se devuelven con el nombre exacto del ERP
(p.ej. `cuentaCobrar`, `activoFijo`) — el caso de uso las matchea
contra `MODULE_TO_SEO_FLAG`.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth.domain.interfaces import SeoPlanRepository

# Lista explícita de columnas — evita traer XMLs, blobs, columnas
# nuevas no mapeadas, y deja claro qué consume SAVI.
_SELECT_PLAN_SQL = """
SELECT
    "activoFijo",
    "cuentaPagar",
    "cuentaCobrar",
    "contabilidad",
    "nomina",
    "mantenimiento",
    "cultivo",
    "carteraFinanciera",
    "inventario",
    "produccionAvicola",
    "bombero",
    "controlPrestamo",
    "herramienta",
    "presupuesto"
FROM "SEO"."Modulo"
ORDER BY "idModulo" DESC
LIMIT 1
"""


class ErpSeoPlanRepository(SeoPlanRepository):
    def __init__(self, erp_engine: AsyncEngine) -> None:
        self._engine = erp_engine

    async def get_active_plan(self) -> dict[str, bool]:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(_SELECT_PLAN_SQL))
            row = result.mappings().first()
        if row is None:
            return {}
        # `bool(None) = False` cubre los campos nullable como `contabilidad`.
        return {str(k): bool(v) for k, v in row.items()}
