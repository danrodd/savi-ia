/**
 * Conocimiento estático de los proveedores para la vista de consumo.
 *
 * Los tres proveedores son un conjunto cerrado y estable (lo define
 * `ProviderDescriptor` en el backend) — a diferencia del modelo, que rota
 * seguido, no hace falta un endpoint para poblar los chips del filtro.
 *
 * `reportsCost` duplica a propósito el flag `reports_cost` del backend
 * (`llm_providers`): es solo presentación (qué leyenda mostrar), y el
 * endpoint de proveedores está reservado a administradores, mientras que
 * "Mi consumo" lo usa cualquier usuario autenticado.
 */
import type { UsageProviderKind } from '../types'

export const USAGE_PROVIDERS: readonly UsageProviderKind[] = ['claude', 'gemini', 'openai']

export const PROVIDER_LABELS: Record<UsageProviderKind, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  openai: 'OpenAI',
}

/** El proveedor informa el costo real del turno (no depende de la tabla
 * de precios del admin). Debe reflejar `reports_cost` en el backend. */
export const REPORTS_COST_BY_PROVIDER: Record<UsageProviderKind, boolean> = {
  claude: true,
  gemini: false,
  openai: false,
}

export function providerLabel(provider: string | null): string {
  if (provider === null) return 'Sin proveedor'
  const key = provider.toLowerCase() as UsageProviderKind
  return PROVIDER_LABELS[key] ?? provider
}
