import { z } from 'zod'

/**
 * Spec de gráfica que el asistente emite dentro de un bloque ```savi-chart.
 * El modelo produce SÓLO datos (nunca código ejecutable): este schema es la
 * frontera de seguridad. Todo lo que no valide cae al fallback de la UI.
 */

export const CHART_TYPES = ['bar', 'line', 'area', 'pie'] as const
export type ChartType = (typeof CHART_TYPES)[number]

const seriesSchema = z.object({
  name: z.string().optional(),
  data: z.array(z.number()),
})

export const chartSpecSchema = z.object({
  type: z.enum(CHART_TYPES),
  title: z.string().optional(),
  labels: z.array(z.string()).optional(),
  series: z.array(seriesSchema).min(1),
  stacked: z.boolean().optional(),
})

export type ChartSpec = z.infer<typeof chartSpecSchema>

export type ChartSpecResult = { ok: true; spec: ChartSpec } | { ok: false; error: string }

/** Parsea + valida el contenido crudo del bloque. Nunca lanza. */
export function parseChartSpec(raw: string): ChartSpecResult {
  let json: unknown
  try {
    json = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'JSON inválido' }
  }
  const result = chartSpecSchema.safeParse(json)
  if (!result.success) {
    return { ok: false, error: result.error.issues[0]?.message ?? 'Spec inválido' }
  }
  return { ok: true, spec: result.data }
}
