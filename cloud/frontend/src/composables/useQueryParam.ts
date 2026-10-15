import { computed, type WritableComputedRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'

interface QueryParamOptions {
  /** Valor cuando la URL no trae el parámetro. */
  fallback?: string | null
  /**
   * Marca para "sin filtro" cuando el valor por defecto no es `null`: sin ella, quitar el
   * parámetro de la URL volvería a aplicar el valor por defecto.
   */
  none?: string
}

/**
 * Un filtro respaldado por la URL (`?clave=valor`): los enlaces compartidos y el botón "atrás"
 * conservan la vista. Cambiar el valor reemplaza la entrada del historial en vez de apilar una.
 */
export function useQueryParam(
  key: string,
  { fallback = null, none }: QueryParamOptions = {},
): WritableComputedRef<string | null> {
  const route = useRoute()
  const router = useRouter()

  return computed<string | null>({
    get() {
      const raw = route.query[key]
      const value = Array.isArray(raw) ? raw[0] : raw
      if (value === undefined || value === null) return fallback
      if (none !== undefined && value === none) return null
      return value === '' ? null : value
    },
    set(value) {
      const query = { ...route.query }
      if (value === null || value === '') {
        if (none !== undefined && fallback !== null) query[key] = none
        else delete query[key]
      } else if (value === fallback) {
        delete query[key]
      } else {
        query[key] = value
      }
      void router.replace({ query })
    },
  })
}

/** Un interruptor respaldado por la URL (`?clave=1`). */
export function useQueryFlag(key: string): WritableComputedRef<boolean> {
  const param = useQueryParam(key)
  return computed({
    get: () => param.value === '1',
    set: (on) => {
      param.value = on ? '1' : null
    },
  })
}
