/**
 * Directiva `v-module` para gating inline en templates.
 *
 * Uso:
 *   <Button v-module="M.CONTABILIDAD">Ver saldos</Button>
 *   <Button v-module:disabled="M.CONTABILIDAD">Ver saldos</Button>
 *
 * - Sin arg (`default`): oculta el elemento con `display: none` y
 *   restaura el display original cuando vuelve el permiso.
 * - Arg `disabled`: agrega `disabled`, `aria-disabled` y opacidad para
 *   feedback visual de "no podés hacer esto".
 *
 * Fail-closed: si el bootstrap no cargó, `puede(code)` retorna false
 * y el elemento queda oculto/deshabilitado.
 *
 * NOTA: la directiva crea su propia instancia del store y NO la
 * reactiva entre updates — Vue llama `updated` cuando el componente
 * vuelve a renderizar, momento en el cual revaluamos.
 */
import type { Directive, DirectiveBinding } from 'vue'

import { usePermisosStore } from '../stores/permisosStore'
import type { ModuleCode } from '../constants'

interface ElState {
  originalDisplay?: string
}

const STATE = new WeakMap<HTMLElement, ElState>()

function getState(el: HTMLElement): ElState {
  let s = STATE.get(el)
  if (!s) {
    s = {}
    STATE.set(el, s)
  }
  return s
}

function applyHide(el: HTMLElement, allowed: boolean): void {
  const state = getState(el)
  if (state.originalDisplay === undefined) state.originalDisplay = el.style.display
  if (allowed) {
    el.style.display = state.originalDisplay
  } else {
    el.style.display = 'none'
  }
}

function applyDisable(el: HTMLElement, allowed: boolean): void {
  if (allowed) {
    el.removeAttribute('disabled')
    el.removeAttribute('aria-disabled')
    el.style.pointerEvents = ''
    el.style.opacity = ''
  } else {
    el.setAttribute('disabled', 'true')
    el.setAttribute('aria-disabled', 'true')
    el.style.pointerEvents = 'none'
    el.style.opacity = '0.5'
  }
}

function evaluate(el: HTMLElement, binding: DirectiveBinding<ModuleCode>): void {
  const store = usePermisosStore()
  const allowed = store.puede(binding.value)
  if (binding.arg === 'disabled') applyDisable(el, allowed)
  else applyHide(el, allowed)
}

export const vModule: Directive<HTMLElement, ModuleCode> = {
  mounted(el, binding) {
    evaluate(el, binding)
  },
  updated(el, binding) {
    evaluate(el, binding)
  },
}
