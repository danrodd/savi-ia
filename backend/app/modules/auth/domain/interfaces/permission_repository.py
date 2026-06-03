"""Puerto a los permisos por formulario del ERP.

Lee `Seguridad.PermisoFormulario` cruzado con `Seguridad.Formulario`
para responder "¿en qué módulos tiene el usuario al menos un permiso
activo en un formulario activo?".

No exponemos el grano fino (formulario, acción) acá — para SAVI alcanza
con saber a qué módulos accede. Si en el futuro hace falta granularidad
mayor, se extiende este puerto sin romper a los actuales.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class PermissionRepository(ABC):
    @abstractmethod
    async def get_modules_with_active_form(self, user_id: int) -> set[str]:
        """Devuelve el set de strings de `Formulario.modulo` donde el
        usuario tiene al menos un permiso activo.

        Los strings se devuelven tal cual están en el ERP (mayúsculas,
        tildes). El caso de uso los matchea contra `ModuleCode`.
        """
