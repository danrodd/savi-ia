"""Clasificación de los módulos del ERP según las reglas de autorización.

Las tres reglas (admin bypass / plan contratado / permisos individuales)
necesitan saber:
- Cuáles son CORE: no se filtran por plan, son del sistema.
- Cuáles son ADMIN_ONLY: solo accesibles si el usuario es administrador.
- Cuáles son VERTICALES y a qué flag de `SEO.Modulo` corresponde cada
  uno.

Las decisiones de mapeo confirmadas con el equipo del ERP están
documentadas en `backend/docs/authentication_system.md`, sección 2.
"""
from __future__ import annotations

from app.modules.auth.domain.value_objects.module_code import ModuleCode

# Módulos transversales del ERP — no se filtran por plan contratado.
# Para aparecer en el set del usuario igual requieren al menos un
# permiso activo en `PermisoFormulario`.
CORE_MODULES: frozenset[ModuleCode] = frozenset({
    ModuleCode.SEGURIDAD,
    ModuleCode.TERCERO,
    ModuleCode.EMPRESA,
    ModuleCode.GENERAL,
    ModuleCode.BUSQUEDA,
})

# Módulos reservados a administradores. No aparecen en el set de un
# usuario no-admin aunque tenga permisos individuales.
ADMIN_ONLY_MODULES: frozenset[ModuleCode] = frozenset({
    ModuleCode.HERRAMIENTA,
})

# Mapeo módulo vertical → nombre de columna booleana en `SEO.Modulo`.
# - VENTA queda atado a `cuentaCobrar` (decisión del equipo del ERP).
# - Los módulos CORE no aparecen acá (no se filtran por plan).
# - HERRAMIENTA no aparece (ADMIN_ONLY, no depende del plan).
MODULE_TO_SEO_FLAG: dict[ModuleCode, str] = {
    ModuleCode.CONTABILIDAD: "contabilidad",
    ModuleCode.NOMINA: "nomina",
    ModuleCode.INVENTARIO: "inventario",
    ModuleCode.CUENTACOBRAR: "cuentaCobrar",
    ModuleCode.CUENTAPAGAR: "cuentaPagar",
    ModuleCode.CARTERAFINANCIERA: "carteraFinanciera",
    ModuleCode.ACTIVOFIJO: "activoFijo",
    ModuleCode.CULTIVO: "cultivo",
    ModuleCode.MANTENIMIENTO: "mantenimiento",
    # VENTA no tiene flag propio: el plan que lo habilita es cuentaCobrar.
    ModuleCode.VENTA: "cuentaCobrar",
}
