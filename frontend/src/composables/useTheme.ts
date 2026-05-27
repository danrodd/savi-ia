import { useStorage } from '@vueuse/core'
import { computed, onUnmounted, ref, watchEffect } from 'vue'
import { STORAGE_KEYS } from '@/lib/storageKeys'

export type ThemeMode = 'light' | 'dark' | 'system'

const MODES: ThemeMode[] = ['light', 'dark', 'system']

function getSystemMedia(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
  return window.matchMedia('(prefers-color-scheme: dark)')
}

function getSystemPreference(): 'light' | 'dark' {
  return getSystemMedia()?.matches ? 'dark' : 'light'
}

export function useTheme() {
  const mode = useStorage<ThemeMode>(STORAGE_KEYS.THEME_MODE, 'system')
  const systemPreference = ref<'light' | 'dark'>(getSystemPreference())

  const systemMedia = getSystemMedia()
  function onSystemChange(e: MediaQueryListEvent): void {
    systemPreference.value = e.matches ? 'dark' : 'light'
  }
  systemMedia?.addEventListener('change', onSystemChange)
  onUnmounted(() => systemMedia?.removeEventListener('change', onSystemChange))

  const resolvedTheme = computed<'light' | 'dark'>(() =>
    mode.value === 'system' ? systemPreference.value : mode.value,
  )

  const isDark = computed(() => resolvedTheme.value === 'dark')

  watchEffect(() => {
    const root = document.documentElement
    if (resolvedTheme.value === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
  })

  function setMode(next: ThemeMode): void {
    mode.value = next
  }

  function cycleTheme(): void {
    const idx = MODES.indexOf(mode.value)
    mode.value = MODES[(idx + 1) % MODES.length] as ThemeMode
  }

  return { mode, resolvedTheme, isDark, setMode, cycleTheme }
}
