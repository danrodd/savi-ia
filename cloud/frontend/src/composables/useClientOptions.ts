import { computed, onMounted, ref } from 'vue'
import { consoleApi } from '@/lib/api'

const MAX_CLIENTS = 200

/**
 * Clientes (id y nombre) para los filtros por cliente, ordenados por nombre. Sin el permiso de
 * ver clientes o ante un fallo la lista queda vacía y la pantalla oculta ese filtro.
 *
 * `selected` es el cliente que ya trae la URL: si no entra en las primeras páginas se agrega
 * igual, para que el filtro nunca quede en blanco.
 */
export function useClientOptions(selected: () => string | null) {
  const clients = ref<{ id: string; name: string }[]>([])

  onMounted(async () => {
    try {
      const page = await consoleApi.clients({ sort: 'name', limit: MAX_CLIENTS })
      clients.value = page.items.map((c) => ({ id: c.id, name: c.name }))
    } catch {
      clients.value = []
    }
  })

  const options = computed(() => {
    const list = clients.value.map((c) => ({ value: c.id, label: c.name }))
    const current = selected()
    if (current && list.length > 0 && !list.some((o) => o.value === current)) {
      list.push({ value: current, label: 'Cliente seleccionado' })
    }
    return list
  })

  return { options }
}
