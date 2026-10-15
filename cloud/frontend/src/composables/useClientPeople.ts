import { onMounted, ref } from 'vue'
import { consoleApi } from '@/lib/api'
import type { Person } from '@/lib/types'

/**
 * Padrón de personas de un cliente (todas las que alguna vez reportaron uso, sin ventana de
 * tiempo) para los selectores de excepciones, reglas y grupos. A diferencia del ranking de
 * uso, incluye a quien lleva meses sin usar SAVI.
 */
export function useClientPeople(clientId: () => string) {
  const people = ref<Person[]>([])

  onMounted(async () => {
    try {
      people.value = await consoleApi.clientPeople(clientId())
    } catch {
      people.value = []
    }
  })

  function isKnown(userRef: string): boolean {
    return people.value.some((p) => p.user_ref === userRef)
  }

  /** Etiqueta legible: el código de usuario si se conoce, si no el seudónimo abreviado. */
  function personLabel(userRef: string): string {
    const found = people.value.find((p) => p.user_ref === userRef)
    if (!found) return `Persona sin actividad reciente (${userRef.slice(0, 8)}…)`
    return found.label ?? `${userRef.slice(0, 8)}…`
  }

  return { people, isKnown, personLabel }
}
