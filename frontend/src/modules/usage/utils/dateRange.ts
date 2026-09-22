/**
 * Traduce un preset de rango a fechas AAAA-MM-DD, en el calendario LOCAL
 * del navegador (no UTC): "Hoy" tiene que ser el día que ve la persona
 * frente a la pantalla, no el día en Greenwich.
 *
 * Lógica pura y sin reactividad a propósito — así se prueba sin montar
 * Pinia, igual que `_period_from_dates` en el backend.
 */
export type RangePreset = 'today' | 'yesterday' | 7 | 30 | 90 | 'custom'

export function toLocalIsoDate(d: Date): string {
  // `toISOString()` normaliza a UTC y corre la fecha un día cerca de
  // medianoche fuera de UTC. Los componentes locales evitan ese corrimiento.
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function presetToRange(
  preset: RangePreset,
  custom: { from: string; to: string },
  now: Date = new Date(),
): { from: string; to: string } {
  if (preset === 'today') {
    const d = toLocalIsoDate(now)
    return { from: d, to: d }
  }
  if (preset === 'yesterday') {
    const y = new Date(now)
    y.setDate(y.getDate() - 1)
    const d = toLocalIsoDate(y)
    return { from: d, to: d }
  }
  if (preset === 'custom') {
    return { from: custom.from, to: custom.to }
  }
  const start = new Date(now)
  start.setDate(start.getDate() - (preset - 1))
  return { from: toLocalIsoDate(start), to: toLocalIsoDate(now) }
}
