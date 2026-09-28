<script setup lang="ts" generic="T extends string">
/**
 * Acciones de una fila detrás de un botón de tres puntos.
 *
 * Con cuatro o cinco botones de texto por fila, las tablas se partían en
 * pantallas medianas y las acciones competían con el contenido. El menú
 * deja una sola columna angosta y agrupa lo destructivo al final.
 */
import { Ellipsis } from 'lucide-vue-next'
import { ref, useTemplateRef } from 'vue'

import Popover from '@/components/ui/Popover.vue'
import type { RowAction } from '../types'

defineProps<{
  actions: RowAction<T>[]
  /** Nombre accesible del botón: "Acciones de Manual de caja". */
  label: string
  disabled?: boolean
}>()
const emit = defineEmits<{ select: [id: T] }>()

const open = ref(false)
const trigger = useTemplateRef<HTMLButtonElement>('trigger')

function pick(action: RowAction<T>): void {
  if (action.disabled) return
  open.value = false
  emit('select', action.id)
}
</script>

<template>
  <button
    ref="trigger"
    type="button"
    class="rowmenu__trigger"
    :aria-label="label"
    aria-haspopup="menu"
    :aria-expanded="open"
    :disabled="disabled"
    @click="open = !open"
  >
    <Ellipsis :size="16" aria-hidden="true" />
  </button>
  <Popover v-model:open="open" :anchor="trigger" align="end" side="bottom" :min-width="190">
    <div role="menu" :aria-label="label">
      <template v-for="action in actions" :key="action.id">
        <div v-if="action.divider" class="rowmenu__divider" aria-hidden="true" />
        <button
          type="button"
          role="menuitem"
          class="rowmenu__item"
          :class="{ 'rowmenu__item--danger': action.danger }"
          :disabled="action.disabled"
          @click="pick(action)"
        >
          <component :is="action.icon" :size="14" aria-hidden="true" />
          {{ action.label }}
        </button>
      </template>
    </div>
  </Popover>
</template>

<style scoped>
.rowmenu__trigger {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
}

.rowmenu__trigger:hover:not(:disabled),
.rowmenu__trigger[aria-expanded='true'] {
  background: var(--surface-subtle);
  color: var(--text);
}

.rowmenu__trigger:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.rowmenu__trigger:disabled {
  cursor: progress;
  opacity: 0.5;
}

.rowmenu__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  font-family: inherit;
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.rowmenu__item:hover:not(:disabled),
.rowmenu__item:focus-visible {
  background: var(--surface-subtle);
  outline: none;
}

.rowmenu__item:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.rowmenu__item--danger {
  color: var(--brand);
}

.rowmenu__item--danger:hover:not(:disabled),
.rowmenu__item--danger:focus-visible {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.rowmenu__divider {
  height: 1px;
  margin: var(--space-1) var(--space-2);
  background: var(--border);
}
</style>
