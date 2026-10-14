import { ref } from 'vue'
import { consoleApi } from './api'

/** Definiciones de métricas (§4.1): se piden una vez y alimentan todos los tooltips. */
const definitions = ref<Record<string, string>>({})
let loading: Promise<void> | null = null

export function useDefinitions() {
  if (!loading && Object.keys(definitions.value).length === 0) {
    loading = consoleApi
      .definitions()
      .then((items) => {
        definitions.value = Object.fromEntries(items.map((i) => [i.key, i.definition]))
      })
      .catch(() => {
        // Sin definiciones el tooltip queda vacío; no es motivo para romper la pantalla.
      })
      .finally(() => {
        loading = null
      })
  }
  return definitions
}

export function resetDefinitionsForTests(): void {
  definitions.value = {}
  loading = null
}
