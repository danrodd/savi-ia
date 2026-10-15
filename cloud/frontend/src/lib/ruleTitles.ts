import { ref } from 'vue'
import { consoleApi } from '@/lib/api'

// Se pide una sola vez por sesión: los títulos de las reglas casi nunca cambian.
const titles = ref<Record<string, string>>({})
let loading: Promise<void> | null = null

/** Título legible de cada regla de alerta (`subscription_due` → "Suscripción por vencer"). */
export function useRuleTitles() {
  if (!loading) {
    loading = consoleApi
      .alertRules()
      .then((rules) => {
        titles.value = Object.fromEntries(rules.map((rule) => [rule.code, rule.title]))
      })
      .catch(() => {
        loading = null
      })
  }
  return (code: string): string => titles.value[code] ?? code
}

export function resetRuleTitlesForTests(): void {
  titles.value = {}
  loading = null
}
