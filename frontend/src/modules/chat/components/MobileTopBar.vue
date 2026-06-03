<script setup lang="ts">
import type { Ref } from 'vue'

import Tooltip from '@/components/ui/Tooltip.vue'
import BrandMark from './BrandMark.vue'
import ShareMenu from './ShareMenu.vue'

defineProps<{
  title?: string
  /** Si está presente, se muestra el botón de compartir conversación.
   *  El padre maneja la lógica de qué pasar (texto, ref, id). */
  shareText?: string
  shareConversationId?: string | null
  shareContentRef?: Ref<HTMLElement | null>
}>()
const emit = defineEmits<{ 'menu-open': []; 'new-chat': [] }>()
</script>

<template>
  <header class="topbar">
    <Tooltip text="Abrir menú" side="bottom">
      <button type="button" class="topbar__btn" aria-label="Abrir menú" @click="emit('menu-open')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12h18M3 6h18M3 18h18" />
        </svg>
      </button>
    </Tooltip>

    <div class="topbar__brand">
      <BrandMark :size="22" label="S" />
      <span class="topbar__title">{{ title ?? 'SAVI' }}</span>
    </div>

    <div class="topbar__actions">
      <!-- Compartir conversación en mobile: usamos el ShareMenu con
           kind='conversation'. Solo se muestra si el padre nos pasó los
           datos necesarios (es decir, hay conversación activa). -->
      <ShareMenu
        v-if="shareText && shareContentRef"
        kind="conversation"
        placement="bottom-end"
        :text="shareText"
        :conversation-id="shareConversationId ?? null"
        :content-ref="shareContentRef"
        :title="title"
      >
        <template #trigger>
          <span class="topbar__btn topbar__btn--icon" aria-label="Compartir conversación">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
              <polyline points="16 6 12 2 8 6" />
              <line x1="12" y1="2" x2="12" y2="15" />
            </svg>
          </span>
        </template>
      </ShareMenu>

      <Tooltip text="Nueva conversación" side="bottom">
        <button type="button" class="topbar__btn" aria-label="Nueva conversación" @click="emit('new-chat')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
        </button>
      </Tooltip>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-sidebar);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 52px;
}

.topbar__btn {
  display: inline-grid;
  place-items: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.topbar__btn--icon {
  width: auto;
  height: auto;
  padding: 8px;
}

.topbar__btn:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.topbar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  flex: 1;
  justify-content: center;
}

.topbar__title {
  font-family: var(--font-display);
  font-weight: var(--fw-semibold);
  font-size: 14px;
  letter-spacing: 0.01em;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
</style>
