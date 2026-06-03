/**
 * `useWelcome` — provee saludo personalizado y sugerencias dinámicas
 * para la pantalla de bienvenida del chat.
 *
 * Saludo: depende de la hora del día y del nombre del usuario.
 * Sugerencias: se filtran por los módulos del usuario y se eligen
 *   aleatoriamente para no repetir siempre las mismas. Los admins ven
 *   sugerencias de todos los módulos.
 *
 * La aleatoriedad se semilla al mount (refresh manual via `reshuffle`).
 */
import { computed, ref, type ComputedRef } from 'vue'

import { useAuthStore } from '@/modules/auth/stores/authStore'
import { MODULE_LABELS, type ModuleCode, usePermisosStore } from '@/modules/permisos'
import { SUGGESTIONS, type ChatSuggestion } from '../suggestions'

interface PreparedSuggestion {
  module: ModuleCode | null
  moduleLabel: string | null
  prompt: string
  label: string
}

export interface WelcomeState {
  greeting: ComputedRef<string>
  firstName: ComputedRef<string>
  subtitle: ComputedRef<string>
  suggestions: ComputedRef<PreparedSuggestion[]>
  reshuffle: () => void
}

const DEFAULT_VISIBLE = 6

function pickGreetingByHour(): string {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Buenos días'
  if (h >= 12 && h < 19) return 'Buenas tardes'
  return 'Buenas noches'
}

function firstNameOf(fullName: string | undefined, fallback: string): string {
  if (!fullName) return fallback
  const trimmed = fullName.trim()
  if (!trimmed) return fallback
  const first = trimmed.split(/\s+/)[0]
  if (!first) return fallback
  // Title case: "JUAN" → "Juan", "carolina" → "Carolina".
  return first.charAt(0).toLocaleUpperCase('es') + first.slice(1).toLocaleLowerCase('es')
}

function shuffle<T>(arr: readonly T[]): T[] {
  const out = arr.slice()
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const tmp = out[i] as T
    out[i] = out[j] as T
    out[j] = tmp
  }
  return out
}

export function useWelcome(visibleCount: number = DEFAULT_VISIBLE): WelcomeState {
  const authStore = useAuthStore()
  const permisosStore = usePermisosStore()

  const seed = ref(0)
  function reshuffle(): void {
    seed.value++
  }

  const firstName = computed(() => firstNameOf(authStore.user?.full_name, authStore.user?.login ?? ''))

  const greeting = computed(() => {
    const name = firstName.value
    return name ? `${pickGreetingByHour()}, ${name}` : pickGreetingByHour()
  })

  const roleLabel = computed(() => (authStore.user?.is_admin ? 'administrador' : 'usuario'))

  const allowedModules = computed<Set<string>>(() => {
    if (permisosStore.isAdmin) {
      // Admins ven sugerencias de todos los módulos del catálogo.
      const all = new Set<string>()
      for (const s of SUGGESTIONS) if (s.module) all.add(s.module)
      return all
    }
    return new Set(permisosStore.modules)
  })

  const subtitle = computed(() => {
    if (permisosStore.isAdmin) {
      return 'Como administrador, tenés acceso a toda la información del ERP. Elegí por dónde arrancar.'
    }
    const count = allowedModules.value.size
    if (count === 0) {
      return 'Pedíme información del ERP o consultame sobre cualquier módulo del sistema.'
    }
    const labels = Array.from(allowedModules.value)
      .map((c) => MODULE_LABELS[c as ModuleCode] ?? c)
      .sort((a, b) => a.localeCompare(b, 'es'))
    const role = roleLabel.value
    const moduleListing =
      labels.length === 1
        ? labels[0]
        : labels.length === 2
        ? `${labels[0]} y ${labels[1]}`
        : `${labels.slice(0, -1).join(', ')} y ${labels[labels.length - 1]}`
    return `Como ${role}, podés consultarme sobre ${moduleListing}.`
  })

  const suggestions = computed<PreparedSuggestion[]>(() => {
    // Trigger reactivo de la semilla — el shuffle es no-determinista pero
    // referenciamos `seed.value` para forzar reevaluación al pedir reshuffle.
    void seed.value

    const eligible = SUGGESTIONS.filter((s) => {
      if (s.module === null) return true
      return allowedModules.value.has(s.module)
    })

    // Mezcla aleatoria, prioridad ligera a las que tienen módulo (más
    // específicas) cuando hay variedad: tomamos primero las con módulo
    // y rellenamos con generales si faltan.
    const shuffled = shuffle(eligible)
    const withModule = shuffled.filter((s) => s.module !== null)
    const general = shuffled.filter((s) => s.module === null)
    const picked = [...withModule, ...general].slice(0, visibleCount)

    return picked.map((s) => ({
      module: s.module,
      moduleLabel: s.module ? MODULE_LABELS[s.module] ?? s.module : null,
      prompt: s.prompt,
      label: s.label ?? s.prompt,
    }))
  })

  return { greeting, firstName, subtitle, suggestions, reshuffle }
}
