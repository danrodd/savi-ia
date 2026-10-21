import { useEventListener } from '@vueuse/core'
import { inject, type Ref } from 'vue'
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router'

/**
 * Navegaciones en las que la persona ya aceptó salir. Una página con varios formularios sucios
 * (Configuración) registra varios avisos: con esto se pregunta una sola vez por navegación.
 * El destino (`to`) es el mismo objeto para todos los avisos de una navegación.
 */
const approved = new WeakSet<object>()

export const LEAVE_MESSAGE = 'Tiene cambios sin guardar. Si sale ahora, se pierden.'

/**
 * Avisa antes de perder cambios sin guardar: al cambiar de pantalla o de pestaña dentro de
 * la consola, y al cerrar o recargar el navegador. Fuera de una ruta (un componente montado
 * suelto, como en los tests) solo vigila el cierre del navegador.
 */
export function useLeaveGuard(isDirty: Ref<boolean>): void {
  if (inject(matchedRouteKey, null)?.value) {
    onBeforeRouteLeave((to) => {
      if (!isDirty.value || approved.has(to)) return true
      const leave = window.confirm(`${LEAVE_MESSAGE} ¿Salir igual?`)
      if (leave) approved.add(to)
      return leave
    })
  }

  useEventListener(window, 'beforeunload', (event: BeforeUnloadEvent) => {
    if (!isDirty.value) return
    event.preventDefault()
  })
}
