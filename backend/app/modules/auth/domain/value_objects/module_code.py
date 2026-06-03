"""Códigos de módulo del ERP — fuente de verdad para autorización.

Los valores coinciden 1:1 con los strings que aparecen en
`Seguridad.Formulario.modulo` del ERP (mayúsculas, con tilde donde
corresponde). Cambiar estos strings rompe la resolución de permisos
contra la BD del ERP — son inmutables.

Los nombres de Python siguen UPPER_SNAKE_CASE; el valor del enum
respeta exactamente el string del ERP (`NÓMINA` con tilde, no `NOMINA`).
"""
from __future__ import annotations

from enum import StrEnum


class ModuleCode(StrEnum):
    """Códigos canónicos de módulo. Coinciden con `Formulario.modulo` del ERP."""

    # Verticales — sujetos al plan contratado en `SEO.Modulo`.
    CONTABILIDAD = "CONTABILIDAD"
    NOMINA = "NÓMINA"
    INVENTARIO = "INVENTARIO"
    CUENTACOBRAR = "CUENTACOBRAR"
    CUENTAPAGAR = "CUENTAPAGAR"
    CARTERAFINANCIERA = "CARTERAFINANCIERA"
    ACTIVOFIJO = "ACTIVOFIJO"
    CULTIVO = "CULTIVO"
    MANTENIMIENTO = "MANTENIMIENTO"
    VENTA = "VENTA"

    # Reservado a administradores. No se entrega a usuarios no-admin.
    HERRAMIENTA = "HERRAMIENTA"

    # Core — transversales del sistema. No se filtran por plan, pero
    # el usuario debe tener al menos un permiso activo en ese módulo
    # para que aparezca en su set.
    SEGURIDAD = "SEGURIDAD"
    TERCERO = "TERCERO"
    EMPRESA = "EMPRESA"
    GENERAL = "GENERAL"
    BUSQUEDA = "BÚSQUEDA"
