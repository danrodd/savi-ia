/**
 * `useModule(code)` — devuelve un ComputedRef<boolean> reactivo que dice
 * si el usuario actual tiene acceso al módulo `code`.
 *
 * Fail-closed: hasta que el bootstrap cargue, retorna `false`. Los admins
 * pasan siempre. Reactividad nativa de Vue: si el set de módulos cambia
 * (por polling o por reload 403), todo lo que use este composable se
 * recalcula.
 */
import { computed, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'

import type { ModuleCode } from '../constants'
import { usePermisosStore } from '../stores/permisosStore'

export function useModule(code: MaybeRefOrGetter<ModuleCode>): ComputedRef<boolean> {
  const store = usePermisosStore()
  return computed(() => store.puede(toValue(code)))
}
