<script setup lang="ts">
import { onClickOutside, useEventListener } from '@vueuse/core'
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'

/**
 * Popover primitivo y reutilizable.
 *
 * Renderiza el contenido vía <Teleport to="body"> para escapar de cualquier
 * contenedor con overflow:hidden|auto (típico problema en sidebars con
 * scroll). Posiciona el panel relativo a un `anchor` HTMLElement con
 * coordenadas fixed, y recalcula la posición en scroll/resize.
 *
 * Cierra automáticamente al hacer click fuera o presionar Esc; el anchor
 * queda exento del click-outside para que el botón trigger pueda alternar
 * el estado sin colisión.
 *
 * Uso típico:
 *   <button ref="triggerRef" @click="open = !open">⋯</button>
 *   <Popover v-model:open="open" :anchor="triggerRef">
 *     <button>Acción 1</button>
 *     <button>Acción 2</button>
 *   </Popover>
 */

const props = withDefaults(
  defineProps<{
    open: boolean
    anchor: HTMLElement | null
    side?: 'top' | 'bottom'
    align?: 'start' | 'center' | 'end'
    offset?: number
    minWidth?: number
  }>(),
  {
    side: 'bottom',
    align: 'end',
    offset: 4,
    minWidth: 180,
  },
)
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const panelRef = useTemplateRef<HTMLDivElement>('panel')
const top = ref(0)
const left = ref(0)

function updatePosition(): void {
  const anchor = props.anchor
  const panel = panelRef.value
  if (!anchor || !panel) return
  const rect = anchor.getBoundingClientRect()
  const panelW = panel.offsetWidth
  const panelH = panel.offsetHeight
  const margin = 8

  let nextTop =
    props.side === 'bottom' ? rect.bottom + props.offset : rect.top - panelH - props.offset
  let nextLeft: number
  if (props.align === 'start') nextLeft = rect.left
  else if (props.align === 'end') nextLeft = rect.right - panelW
  else nextLeft = rect.left + (rect.width - panelW) / 2

  // Clamp a viewport con un margen mínimo para que no se desborde.
  nextLeft = Math.max(margin, Math.min(nextLeft, window.innerWidth - panelW - margin))
  nextTop = Math.max(margin, Math.min(nextTop, window.innerHeight - panelH - margin))

  top.value = nextTop
  left.value = nextLeft
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    await nextTick()
    updatePosition()
    panelRef.value?.querySelector<HTMLElement>('button, [tabindex]:not([tabindex="-1"])')?.focus()
  },
)

useEventListener(
  'scroll',
  () => {
    if (props.open) updatePosition()
  },
  { capture: true, passive: true },
)
useEventListener('resize', () => {
  if (props.open) updatePosition()
})
useEventListener('keydown', (e: KeyboardEvent) => {
  if (props.open && e.key === 'Escape') {
    e.preventDefault()
    emit('update:open', false)
  }
})

const anchorRef = computed(() => props.anchor)
onClickOutside(
  panelRef,
  () => {
    if (props.open) emit('update:open', false)
  },
  { ignore: [anchorRef] },
)

const transformOrigin = computed(() => {
  const vert = props.side === 'top' ? 'bottom' : 'top'
  const horz = props.align === 'start' ? 'left' : props.align === 'center' ? 'center' : 'right'
  return `${vert} ${horz}`
})
</script>

<template>
  <Teleport to="body">
    <Transition name="popover">
      <div
        v-if="open"
        ref="panel"
        class="popover"
        :style="{
          top: `${top}px`,
          left: `${left}px`,
          minWidth: `${minWidth}px`,
          transformOrigin,
        }"
        role="dialog"
      >
        <slot />
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.popover {
  position: fixed;
  z-index: 1000;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  padding: var(--space-1);
  color: var(--text);
  font-family: var(--font-sans);
}

.popover-enter-active,
.popover-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.popover-enter-from,
.popover-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(-2px);
}
</style>
