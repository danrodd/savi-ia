/** Nombre, de usted, de la categoría de un turno fallido. */
const CATEGORIES: Record<string, string> = {
  provider_busy: 'Proveedor saturado',
  provider_refused: 'El proveedor no quiso responder',
  provider_error: 'Proveedor no disponible',
  internal_error: 'Falla interna',
}

export function failedTurnCategory(code: string | null): string {
  if (!code) return 'Sin categoría'
  return CATEGORIES[code] ?? 'Sin categoría'
}
