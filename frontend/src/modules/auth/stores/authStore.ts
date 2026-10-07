/**
 * Pinia store de auth.
 *
 * State persistido en `localStorage` para sobrevivir a recargas:
 * - `access_token`, `refresh_token`, `user`.
 *
 * Maneja una **cola de refresh**: cuando varias requests reciben 401 al
 * mismo tiempo, solo UNA dispara el refresh; las demás esperan en una
 * promesa compartida. Sin la cola, cada request dispararía un refresh
 * independiente y rotaríamos N veces el token con N-1 fallos.
 *
 * El logout limpia el store + storage y avisa al backend (idempotente).
 */
import { computed, ref } from 'vue'

import { defineStore } from 'pinia'

import { STORAGE_KEYS } from '@/lib/storageKeys'
import { authService, AuthRequestError } from '../services/authService'
import type { AuthUser, LoginPayload, TokenResponse } from '../types'

function readString(key: string): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(key)
}

function writeString(key: string, value: string | null): void {
  if (typeof window === 'undefined') return
  if (value === null) window.localStorage.removeItem(key)
  else window.localStorage.setItem(key, value)
}

function readUser(): AuthUser | null {
  const raw = readString(STORAGE_KEYS.AUTH_USER)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(readString(STORAGE_KEYS.ACCESS_TOKEN))
  const refreshToken = ref<string | null>(readString(STORAGE_KEYS.REFRESH_TOKEN))
  const user = ref<AuthUser | null>(readUser())

  // Promesa compartida del refresh en curso (si la hay). Cuando una
  // request recibe 401, llama a `ensureFreshAccessToken()`: si ya hay un
  // refresh en vuelo, se espera al mismo; si no, dispara uno y lo
  // memoriza para el resto.
  let inflightRefresh: Promise<string> | null = null

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)

  function persist(tokens: TokenResponse): void {
    accessToken.value = tokens.access_token
    refreshToken.value = tokens.refresh_token
    user.value = tokens.user
    writeString(STORAGE_KEYS.ACCESS_TOKEN, tokens.access_token)
    writeString(STORAGE_KEYS.REFRESH_TOKEN, tokens.refresh_token)
    writeString(STORAGE_KEYS.AUTH_USER, JSON.stringify(tokens.user))
  }

  function clearSession(): void {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    writeString(STORAGE_KEYS.ACCESS_TOKEN, null)
    writeString(STORAGE_KEYS.REFRESH_TOKEN, null)
    writeString(STORAGE_KEYS.AUTH_USER, null)
    // Las imágenes del chat quedan en memoria como URLs locales: se
    // descartan al salir para que no las vea quien entre después.
    void import('@/modules/chat/lib/attachmentBlobCache').then((m) => m.clearAttachmentCache())
  }

  async function login(payload: LoginPayload): Promise<void> {
    const tokens = await authService.login(payload)
    persist(tokens)
    // Carga del bootstrap de permisos justo tras el login — evita que
    // el primer render post-login muestre la UI con set vacío (fail-closed).
    // Importamos perezosamente para no introducir un ciclo al import-time.
    const { usePermisosStore } = await import('@/modules/permisos')
    const permisos = usePermisosStore()
    await permisos.cargarBootstrap()
  }

  async function logout(): Promise<void> {
    const rt = refreshToken.value
    clearSession()
    if (rt) await authService.logout(rt)
  }

  /**
   * Devuelve un access token válido. Si hubo un 401, llama al backend
   * con el refresh para rotar. Si el refresh falla → limpia la sesión
   * y propaga el error (el caller redirige al login).
   */
  async function ensureFreshAccessToken(): Promise<string> {
    if (inflightRefresh) return inflightRefresh
    const rt = refreshToken.value
    if (!rt) throw new AuthRequestError('Sin refresh token', 401)
    inflightRefresh = (async () => {
      try {
        const tokens = await authService.refresh(rt)
        persist(tokens)
        return tokens.access_token
      } catch (err) {
        clearSession()
        throw err
      } finally {
        inflightRefresh = null
      }
    })()
    return inflightRefresh
  }

  async function fetchMe(): Promise<void> {
    const at = accessToken.value
    if (!at) return
    try {
      const me = await authService.me(at)
      user.value = me
      writeString(STORAGE_KEYS.AUTH_USER, JSON.stringify(me))
    } catch (err) {
      if (err instanceof AuthRequestError && err.status === 401) {
        clearSession()
      }
      throw err
    }
  }

  return {
    accessToken,
    refreshToken,
    user,
    isAuthenticated,
    login,
    logout,
    clearSession,
    ensureFreshAccessToken,
    fetchMe,
  }
})
