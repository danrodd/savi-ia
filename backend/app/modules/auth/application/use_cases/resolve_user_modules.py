"""Use case que resuelve los módulos del ERP a los que el usuario accede.

Las tres reglas (en orden):

1. **Admin bypass**: si `user.is_admin`, accede a todos los módulos
   declarados en `ModuleCode` (incluido HERRAMIENTA).

2. **Permisos individuales**: módulos donde tiene al menos un permiso
   activo en `PermisoFormulario`. Strings que no matchean con
   `ModuleCode` (módulos nuevos no mapeados) se ignoran silenciosamente
   — falla cerrado.

3. **Plan contratado**: para módulos verticales (los que tienen flag
   en `MODULE_TO_SEO_FLAG`), el flag en `SEO.Modulo` debe estar en
   `true`. Si el plan no lo cubre, se descarta aunque el usuario tenga
   permisos individuales. Los CORE_MODULES no se filtran por plan.
   HERRAMIENTA es ADMIN_ONLY: el no-admin nunca lo recibe.

Devuelve también el `version_hash` SHA-256 estable del set, para que
el frontend pueda detectar cambios sin recargar el bootstrap completo.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.modules.auth.domain.interfaces import (
    PermissionRepository,
    SeoPlanRepository,
)
from app.modules.auth.domain.value_objects import (
    ADMIN_ONLY_MODULES,
    MODULE_TO_SEO_FLAG,
    ModuleCode,
)


@dataclass(frozen=True, slots=True)
class UserModulesResolution:
    """Resultado del resolve: el set de módulos + el hash de versión."""

    modules: frozenset[ModuleCode]
    version: str


class ResolveUserModulesUseCase:
    def __init__(
        self,
        permission_repo: PermissionRepository,
        seo_plan_repo: SeoPlanRepository,
    ) -> None:
        self._permissions = permission_repo
        self._plan = seo_plan_repo

    async def execute(self, user_id: int, *, is_admin: bool) -> UserModulesResolution:
        if is_admin:
            modules = frozenset(ModuleCode)
            return UserModulesResolution(modules=modules, version=_hash(user_id, modules))

        # Strings que el ERP guardó en `Formulario.modulo` para este user.
        raw_modules = await self._permissions.get_modules_with_active_form(user_id)

        # Match con ModuleCode. Strings desconocidos se ignoran (fail-closed).
        candidate: set[ModuleCode] = set()
        for raw in raw_modules:
            try:
                candidate.add(ModuleCode(raw))
            except ValueError:
                # Módulo no mapeado en SAVI — se ignora silencioso.
                continue

        # ADMIN_ONLY no aplica a no-admin.
        candidate -= ADMIN_ONLY_MODULES

        # Filtrar verticales por plan contratado.
        plan = await self._plan.get_active_plan()
        filtered: set[ModuleCode] = set()
        for module in candidate:
            flag = MODULE_TO_SEO_FLAG.get(module)
            if flag is None:
                # CORE — no se filtra por plan.
                filtered.add(module)
                continue
            if plan.get(flag, False):
                filtered.add(module)

        modules = frozenset(filtered)
        return UserModulesResolution(modules=modules, version=_hash(user_id, modules))


def _hash(user_id: int, modules: frozenset[ModuleCode]) -> str:
    """Hash determinista del estado de autorización del usuario.

    Cambia si cambia el set de módulos o el user_id. El frontend lo
    compara contra el cacheado para detectar cambios en caliente.
    """
    sorted_codes = ",".join(sorted(m.value for m in modules))
    payload = f"{user_id}:{sorted_codes}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
