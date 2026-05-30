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
