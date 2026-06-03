"""Impl `PermissionRepository` contra `Seguridad.PermisoFormulario`.

Resuelve "¿en qué módulos tiene el usuario al menos un permiso activo
en un formulario activo?". El cross-join entre PermisoFormulario y
Formulario filtra por `estado=true` en ambos lados para descartar
permisos lógicamente borrados y formularios deshabilitados.

Los strings devueltos vienen de `Formulario.modulo` tal cual (mayúsculas,
con tilde donde corresponde). El caso de uso los matchea contra
`ModuleCode`.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth.domain.interfaces import PermissionRepository

_SELECT_MODULES_SQL = """
SELECT DISTINCT f."modulo"
FROM "Seguridad"."PermisoFormulario" pf
JOIN "Seguridad"."Formulario" f ON f."idFormulario" = pf."idFormulario"
WHERE pf."idUsuario" = :user_id
  AND pf."estado" = true
  AND f."estado" = true
"""


class ErpPermissionRepository(PermissionRepository):
    def __init__(self, erp_engine: AsyncEngine) -> None:
        self._engine = erp_engine

    async def get_modules_with_active_form(self, user_id: int) -> set[str]:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(_SELECT_MODULES_SQL), {"user_id": user_id})
            rows = result.scalars().all()
        return {str(m) for m in rows}
