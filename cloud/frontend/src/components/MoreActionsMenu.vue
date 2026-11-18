<script setup lang="ts" generic="T extends string">
import { Popover } from '@savi/ui'
import { ChevronDown } from 'lucide-vue-next'
import { type Component, ref, useTemplateRef } from 'vue'

export interface MenuAction<K extends string> {
  id: K
  label: string
  icon: Component
  /** Lo destructivo va al final, separado y en rojo: no compite con lo habitual. */
  danger?: boolean
}

defineProps<{ actions: MenuAction<T>[]; label?: string }>()
const emit = defineEmits<{ select: [id: T] }>()

const open = ref(false)
const trigger = useTemplateRef<HTMLButtonElement>('trigger')

function pick(id: T): void {
  open.value = false
  emit('select', id)
}
</script>

<template>
  <button
    ref="trigger"
    type="button"
    class="more__trigger"
    aria-haspopup="menu"
    :aria-expanded="open"
    data-test="more-actions"
    @click="open = !open"
  >
    {{ label ?? 'Más acciones' }}
    <ChevronDown :size="14" aria-hidden="true" />
  </button>
  <Popover v-model:open="open" :anchor="trigger" align="end" side="bottom" :min-width="220">
    <div role="menu" :aria-label="label ?? 'Más acciones'">
      <template v-for="(action, index) in actions" :key="action.id">
        <div
          v-if="action.danger && index > 0 && !actions[index - 1]?.danger"
          class="more__divider"
          aria-hidden="true"
        />
        <button
          type="button"
          role="menuitem"
          class="more__item"
          :class="{ 'more__item--danger': action.danger }"
          :data-test="`action-${action.id}`"
          @click="pick(action.id)"
        >
          <component :is="action.icon" :size="14" aria-hidden="true" />
          {{ action.label }}
        </button>
      </template>
    </div>
  </Popover>
</template>

<style scoped>
.more__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 36px;
  padding: 0 var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font: inherit;
  font-size: 13.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.more__trigger:hover,
.more__trigger[aria-expanded='true'] {
  background: var(--surface-subtle);
}

.more__trigger:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.more__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: var(--fw-medium);
  text-align: left;
  cursor: pointer;
}

.more__item:hover,
.more__item:focus-visible {
  background: var(--surface-subtle);
  outline: none;
}

.more__item--danger {
  color: var(--text-danger);
}

.more__divider {
  height: 1px;
  margin: var(--space-1) var(--space-2);
  background: var(--border);
}
</style>
