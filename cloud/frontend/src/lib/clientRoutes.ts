/**
 * Destinos dentro del detalle de un cliente. Una sola tabla evita que cada enlace (puesta en
 * marcha, vacíos, alertas) escriba su propia URL: si una pestaña se mueve, se cambia aquí.
 */
export type ClientSection =
  | 'resumen'
  | 'plan'
  | 'instalaciones'
  | 'ia'
  | 'acceso'
  | 'instancias'
  | 'sucursales'
  | 'personas'
  | 'vinculacion'
  | 'alertas'

/** Secciones de la página Configuración, en el orden en que se muestran. */
export const CONFIG_SECTIONS = ['instalaciones', 'ia', 'acceso'] as const
export type ConfigSection = (typeof CONFIG_SECTIONS)[number]

/** Subsecciones de Operación, en el orden de su selector. */
export const OPERATION_SECTIONS = ['instancias', 'sucursales', 'personas'] as const
export type OperationSection = (typeof OPERATION_SECTIONS)[number]

function isConfigSection(section: ClientSection): section is ConfigSection {
  return (CONFIG_SECTIONS as readonly string[]).includes(section)
}

function isOperationSection(section: ClientSection): section is OperationSection {
  return (OPERATION_SECTIONS as readonly string[]).includes(section)
}

/** Ruta de una sección del cliente; las de Configuración llevan su ancla (`#ia`). */
export function clientPath(clientId: string, section: ClientSection): string {
  const base = `/clientes/${clientId}`
  if (isConfigSection(section)) return `${base}/configuracion#${section}`
  if (isOperationSection(section)) return `${base}/operacion/${section}`
  return `${base}/${section}`
}

/**
 * URLs anteriores a la reorganización de pestañas → su destino actual. Cada una conserva un
 * marcador o subruta, así un enlace guardado cae en la misma sección.
 */
export const LEGACY_CLIENT_TABS: Record<string, ClientSection> = {
  suscripcion: 'plan',
  politica: 'instalaciones',
  ia: 'ia',
  acceso: 'acceso',
  instancias: 'instancias',
  sucursales: 'sucursales',
  usuarios: 'personas',
}
