import { useEventListener } from '@vueuse/core'
import { inject, type Ref } from 'vue'
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router'

export const LEAVE_MESSAGE = 'Tenés cambios sin guardar. Si salís ahora, se pierden.'

/**
 * Avisa antes de perder cambios sin guardar: al cambiar de pantalla o de pestaña dentro de
 * la consola, y al cerrar o recargar el navegador. Fuera de una ruta (un componente montado
 * suelto, como en los tests) solo vigila el cierre del navegador.
 */
export function useLeaveGuard(isDirty: Ref<boolean>): void {
  if (inject(matchedRouteKey, null)?.value) {
    onBeforeRouteLeave(() => {
      if (!isDirty.value) return true
      return window.confirm(`${LEAVE_MESSAGE} ¿Salir igual?`)
    })
  }

  useEventListener(window, 'beforeunload', (event: BeforeUnloadEvent) => {
    if (!isDirty.value) return
    event.preventDefault()
  })
}
