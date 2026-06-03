<script setup lang="ts">
import Popover from '@/components/ui/Popover.vue'

defineProps<{
  open: boolean
  anchor: HTMLElement | null
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  rename: []
  share: []
  delete: []
}>()

function pick(action: 'rename' | 'share' | 'delete'): void {
  emit('update:open', false)
  if (action === 'rename') emit('rename')
  else if (action === 'share') emit('share')
  else emit('delete')
}
</script>

<template>
  <Popover
    :open="open"
    :anchor="anchor"
    align="end"
    side="bottom"
    :min-width="180"
    @update:open="emit('update:open', $event)"
  >
    <button type="button" class="menu__item" role="menuitem" @click="pick('rename')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z" />
      </svg>
      Renombrar
    </button>
    <!-- Compartir: acción rápida (Web Share o copiar link). Para el export
         completo (HTML/PDF/MD) el usuario abre la conversación y usa el
         menú in-chat con las 5 opciones — no duplicamos ese popover acá
         para evitar nesting de popovers (UX confusa). -->
    <button type="button" class="menu__item" role="menuitem" @click="pick('share')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
        <polyline points="16 6 12 2 8 6" />
        <line x1="12" y1="2" x2="12" y2="15" />
      </svg>
      Compartir
    </button>
    <div class="menu__divider" aria-hidden="true" />
    <button
      type="button"
      class="menu__item menu__item--danger"
      role="menuitem"
      @click="pick('delete')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 6h18" />
        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
        <path d="M10 11v6M14 11v6" />
      </svg>
      Eliminar
    </button>
  </Popover>
</template>

<style scoped>
.menu__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  font-family: inherit;
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.menu__item:hover,
.menu__item:focus-visible {
  background: var(--surface-subtle);
  outline: none;
}

.menu__item--danger {
  color: var(--brand);
}

.menu__item--danger:hover,
.menu__item--danger:focus-visible {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.menu__divider {
  height: 1px;
  background: var(--border);
  margin: var(--space-1) var(--space-2);
}
</style>
