import { onMounted, ref } from 'vue'
import { consoleApi } from '@/lib/api'

const TYPE_LABEL: Record<string, string> = {
  client: 'Cliente',
  instance: 'Instancia',
  alert: 'Alerta',
  alert_rule: 'Regla de alerta',
  staff: 'Usuario del equipo',
  enrollment_token: 'Token de vinculación',
}

export interface TargetView {
  /** Texto legible: el nombre si se resolvió, si no el tipo en español con el id abreviado. */
  label: string
  /** Pantalla a la que lleva, si el objeto tiene una. */
  to: string | null
}

/**
 * Nombres legibles de los objetos de la auditoría. Carga clientes e instancias una vez (listas
 * completas y baratas); lo que no se resuelve cae al tipo y el id corto. Un fallo no bloquea.
 */
export function useTargetNames() {
  const clients = ref(new Map<string, string>())
  const instances = ref(new Map<string, string>())

  onMounted(async () => {
    try {
      const page = await consoleApi.clients({ sort: 'name', limit: 200 })
      clients.value = new Map(page.items.map((x) => [x.id, x.name]))
    } catch {
      // Sin nombres, se muestra el tipo y el id corto.
    }
    try {
      const list = await consoleApi.instances({})
      instances.value = new Map(list.map((x) => [x.id, x.name]))
    } catch {
      // Ídem.
    }
  })

  function describe(type: string | null, id: string | null): TargetView | null {
    if (!type && !id) return null
    const typeLabel = type ? (TYPE_LABEL[type] ?? type) : 'Objeto'
    const short = id ? `${id.slice(0, 8)}…` : ''
    if (type === 'client' && id) {
      const name = clients.value.get(id)
      return { label: name ? `Cliente ${name}` : `${typeLabel} ${short}`, to: `/clientes/${id}` }
    }
    if (type === 'instance' && id) {
      const name = instances.value.get(id)
      return {
        label: name ? `Instancia ${name}` : `${typeLabel} ${short}`,
        to: `/instancias/${id}`,
      }
    }
    return { label: `${typeLabel} ${short}`.trim(), to: null }
  }

  return { describe }
}
