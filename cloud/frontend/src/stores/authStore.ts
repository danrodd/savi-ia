import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/lib/api'
import { ApiError } from '@/lib/http'
import type { LoginStep, MfaSetup, Permission, StaffUser, TokenResponse } from '@/lib/types'

/** Paso en el que está la pantalla de acceso. */
export type AuthStep =
  | { kind: 'credentials' }
  | { kind: 'mfa'; token: string }
  | { kind: 'setup'; token: string; setup: MfaSetup; mustChangePassword: boolean }

export const useAuthStore = defineStore('auth', () => {
  // El access token vive solo en memoria: recargar la página lo renueva con la cookie.
  const accessToken = ref<string | null>(null)
  const user = ref<StaffUser | null>(null)
  const restored = ref(false)
  let inflightRefresh: Promise<string | null> | null = null

  const isAuthenticated = computed(() => accessToken.value !== null && user.value !== null)

  function can(permission: Permission): boolean {
    return user.value?.permissions.includes(permission) ?? false
  }

  function setSession(response: TokenResponse): void {
    accessToken.value = response.access_token
    user.value = response.user
  }

  function clearSession(): void {
    accessToken.value = null
    user.value = null
  }

  /** Renueva con la cookie HttpOnly. Las llamadas simultáneas comparten una sola petición. */
  function refresh(): Promise<string | null> {
    if (inflightRefresh) return inflightRefresh
    inflightRefresh = authApi
      .refresh()
      .then((response) => {
        setSession(response)
        return response.access_token
      })
      .catch(() => {
        clearSession()
        return null
      })
      .finally(() => {
        inflightRefresh = null
      })
    return inflightRefresh
  }

  /** Intenta recuperar la sesión al abrir la consola (una sola vez). */
  async function restore(): Promise<void> {
    if (restored.value) return
    restored.value = true
    if (!accessToken.value) await refresh()
  }

  async function submitCredentials(email: string, password: string): Promise<AuthStep> {
    const step: LoginStep = await authApi.login(email, password)
    if (step.status === 'mfa_required') return { kind: 'mfa', token: step.token }
    const setup = await authApi.beginSetup(step.token)
    return {
      kind: 'setup',
      token: step.token,
      setup,
      mustChangePassword: step.must_change_password,
    }
  }

  async function submitMfa(token: string, code: string): Promise<void> {
    setSession(await authApi.mfa(token, code))
  }

  async function confirmSetup(
    token: string,
    code: string,
    newPassword: string | null,
  ): Promise<void> {
    setSession(await authApi.confirmSetup(token, code, newPassword))
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch (error) {
      if (!(error instanceof ApiError)) throw error
    } finally {
      clearSession()
    }
  }

  return {
    accessToken,
    user,
    restored,
    isAuthenticated,
    can,
    refresh,
    restore,
    clearSession,
    submitCredentials,
    submitMfa,
    confirmSetup,
    logout,
  }
})
