/**
 * Espejo manual del enum `ModuleCode` del backend.
 *
 * REGLA CRÍTICA: cualquier cambio acá se replica en
 * `backend/app/modules/auth/domain/value_objects/module_code.py` y
 * viceversa. Las strings tienen que coincidir EXACTO (mayúsculas, tildes).
 * La fricción es deliberada — fuerza la sincronización.
 */

export const M = {
  // Verticales (sujetos a plan en SEO.Modulo)
  CONTABILIDAD: 'CONTABILIDAD',
  NOMINA: 'NÓMINA',
  INVENTARIO: 'INVENTARIO',
  CUENTACOBRAR: 'CUENTACOBRAR',
  CUENTAPAGAR: 'CUENTAPAGAR',
  CARTERAFINANCIERA: 'CARTERAFINANCIERA',
  ACTIVOFIJO: 'ACTIVOFIJO',
  CULTIVO: 'CULTIVO',
  MANTENIMIENTO: 'MANTENIMIENTO',
  VENTA: 'VENTA',
  // Reservado a administradores
  HERRAMIENTA: 'HERRAMIENTA',
  // Core — transversales del sistema
  SEGURIDAD: 'SEGURIDAD',
  TERCERO: 'TERCERO',
  EMPRESA: 'EMPRESA',
  GENERAL: 'GENERAL',
  BUSQUEDA: 'BÚSQUEDA',
} as const

export type ModuleCode = (typeof M)[keyof typeof M]

/** Etiqueta legible para la UI — usa en chips, sidebar, perfil. */
export const MODULE_LABELS: Record<ModuleCode, string> = {
  CONTABILIDAD: 'Contabilidad',
  'NÓMINA': 'Nómina',
  INVENTARIO: 'Inventario',
  CUENTACOBRAR: 'Cuentas por cobrar',
  CUENTAPAGAR: 'Cuentas por pagar',
  CARTERAFINANCIERA: 'Cartera financiera',
  ACTIVOFIJO: 'Activos fijos',
  CULTIVO: 'Cultivo',
  MANTENIMIENTO: 'Mantenimiento',
  VENTA: 'Ventas',
  HERRAMIENTA: 'Herramientas',
  SEGURIDAD: 'Seguridad',
  TERCERO: 'Terceros',
  EMPRESA: 'Empresa',
  GENERAL: 'General',
  'BÚSQUEDA': 'Búsqueda',
}
