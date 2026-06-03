/**
 * Puente entre el `HttpClient` (no-Vue) y el `authStore` / `router`.
 *
 * Por qué este puente: `HttpClient` se instancia como módulo plano, sin
 * setup() ni `useAuthStore()` disponibles en su scope. Si importáramos
 * `useAuthStore` directamente desde HttpClient, generaríamos un ciclo
 * (HttpClient ↔ authStore ↔ authService usado por el store).
 *
 * En su lugar, `main.ts` (tras crear pinia + router) llama a
 * `installAuthBridge()` con callbacks que cierran sobre el store y el
 * router ya inicializados. HttpClient solo usa esos callbacks.
 */

type RedirectToLogin = (nextPath?: string) => void

interface AuthBridge {
  getAccessToken(): string | null
  refreshAccessToken(): Promise<string>
  clearSession(): void
  redirectToLogin: RedirectToLogin
  /**
   * Recarga el bootstrap de permisos del usuario.
   * Disparado por el HttpClient cuando un 403 con
   * `errorCode: module_access_denied` indica caché stale.
   */
  reloadPermisos(): void
}

let bridge: AuthBridge | null = null

export function installAuthBridge(impl: AuthBridge): void {
  bridge = impl
}

export function getAuthBridge(): AuthBridge {
  if (!bridge) {
    throw new Error(
      'authBridge no instalado: llamá installAuthBridge() en main.ts antes de cualquier request HTTP.',
    )
  }
  return bridge
}
