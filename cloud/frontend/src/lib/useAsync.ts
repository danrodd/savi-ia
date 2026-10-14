import { type Ref, ref, shallowRef } from 'vue'
import { ApiError } from './http'

export interface AsyncState<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  reload: () => Promise<void>
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Ocurrió un error inesperado.'
}

/** Carga un recurso y expone `loading`/`error`. La última llamada gana (evita pisar datos). */
export function useAsync<T>(loader: () => Promise<T>, immediate = true): AsyncState<T> {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<string | null>(null)
  let sequence = 0

  async function reload(): Promise<void> {
    const mine = ++sequence
    loading.value = true
    error.value = null
    try {
      const result = await loader()
      if (mine === sequence) data.value = result
    } catch (e) {
      if (mine === sequence) error.value = errorMessage(e)
    } finally {
      if (mine === sequence) loading.value = false
    }
  }

  if (immediate) void reload()
  return { data, loading, error, reload }
}
