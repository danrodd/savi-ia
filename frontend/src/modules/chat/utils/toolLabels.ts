/**
 * Etiquetas amigables para mostrar al usuario cuando una tool entra en
 * juego. La spec del backend (sección 6) prohíbe mostrar nombres técnicos
 * de tools al usuario funcional — solo el label traducido.
 *
 * Tools que mapean al mismo label se agrupan visualmente en una sola pill
 * con contador (×N).
 */

const TOOL_LABELS: Record<string, string> = {
  info_empresa: 'Consultando datos de tu empresa',
  mcp__savi__info_empresa: 'Consultando datos de tu empresa',
  mcp__savi__consultar_libre: 'Consultando información del ERP',
  mcp__savi__consultar_datos: 'Consultando información del ERP',
}

const DEFAULT_LABEL = 'Procesando información'

export function getToolLabel(name: string): string {
  return TOOL_LABELS[name] ?? DEFAULT_LABEL
}
