/**
 * Pinia store del subsistema de permisos.
 *
 * Estado:
 * - `modules`: Set<string> de códigos de módulo del usuario.
 * - `version`: hash del estado actual; null si no se cargó todavía.
 * - `isAdmin`: bypass del usuario actual.
 * - `loaded`: si ya se hizo el bootstrap inicial.
 *
 * Reglas:
 * - `puede(code)` retorna `false` si `loaded === false` (fail-closed).
 * - El bootstrap solo se llama si hay sesión (usaAuthStore.isAuthenticated).
 * - El polling y el reload-por-403 viven en composables aparte;
 *   acá solo está la API pura de estado + carga.
 */
import { computed, ref } from 'vue'

import { defineStore } from 'pinia'

import { STORAGE_KEYS } from '@/lib/storageKeys'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import type { ModuleCode } from '../constants'
import { permisosService } from '../services/permisosService'

function readArray(key: string): string[] | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(key)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (Array.isArray(parsed)) return parsed.filter((s): s is string => typeof s === 'string')
    return null
  } catch {
    return null
  }
}

function writeArray(key: string, value: string[] | null): void {
  if (typeof window === 'undefined') return
  if (value === null) window.localStorage.removeItem(key)
  else window.localStorage.setItem(key, JSON.stringify(value))
}

function readString(key: string): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(key)
}

function writeString(key: string, value: string | null): void {
  if (typeof window === 'undefined') return
  if (value === null) window.localStorage.removeItem(key)
  else window.localStorage.setItem(key, value)
}

export const usePermisosStore = defineStore('permisos', () => {
  const cachedModules = readArray(STORAGE_KEYS.PERMISOS_MODULES)
  const cachedVersion = readString(STORAGE_KEYS.PERMISOS_VERSION)

  const modules = ref<Set<string>>(new Set(cachedModules ?? []))
  const version = ref<string | null>(cachedVersion)
  // Si arrancamos con caché de localStorage, marcamos `loaded`. Igual el
  // polling va a reconciliar si la versión cambió.
  const loaded = ref<boolean>(cachedModules !== null && cachedVersion !== null)
  const loading = ref<boolean>(false)

  const authStore = useAuthStore()
  const isAdmin = computed<boolean>(() => authStore.user?.is_admin ?? false)

  function puede(code: ModuleCode): boolean {
    if (!loaded.value) return false
    if (isAdmin.value) return true
    return modules.value.has(code)
  }

  async function cargarBootstrap(): Promise<void> {
    if (!authStore.isAuthenticated) return
    loading.value = true
    try {
      const bs = await permisosService.getBootstrap()
      modules.value = new Set(bs.modules)
      version.value = bs.version
      loaded.value = true
      writeArray(STORAGE_KEYS.PERMISOS_MODULES, bs.modules)
      writeString(STORAGE_KEYS.PERMISOS_VERSION, bs.version)
    } finally {
      loading.value = false
    }
  }

  async function verificarVersion(): Promise<boolean> {
    // Devuelve true si la versión cambió (y ya se recargó el bootstrap).
    if (!authStore.isAuthenticated || !loaded.value) return false
    try {
      const { version: remote } = await permisosService.getVersion()
      if (remote !== version.value) {
        await cargarBootstrap()
        return true
      }
      return false
    } catch {
      // Silencioso: si el polling falla, el siguiente intento reintenta.
      return false
    }
  }

  function clearPermisos(): void {
    modules.value = new Set()
    version.value = null
    loaded.value = false
    writeArray(STORAGE_KEYS.PERMISOS_MODULES, null)
    writeString(STORAGE_KEYS.PERMISOS_VERSION, null)
  }

  return {
    modules,
    version,
    loaded,
    loading,
    isAdmin,
    puede,
    cargarBootstrap,
    verificarVersion,
    clearPermisos,
  }
})
