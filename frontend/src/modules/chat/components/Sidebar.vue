<script setup lang="ts">
import type { Conversation } from '../types'
import BrandMark from './BrandMark.vue'
import ConversationItem from './ConversationItem.vue'
import ThemeToggle from './ThemeToggle.vue'

defineProps<{
  conversations: Conversation[]
  activeId: string | null
  loading: boolean
  open: boolean
  mobile: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  rename: [id: string, title: string]
  'new-chat': []
  close: []
}>()
</script>

<template>
  <div
    v-if="mobile && open"
    class="sidebar-backdrop"
    aria-hidden="true"
    @click="emit('close')"
  />
  <aside
    class="sidebar"
    :class="{ 'sidebar--mobile': mobile, 'sidebar--open': open }"
    :aria-hidden="mobile && !open"
  >
    <header class="sidebar__brand">
      <BrandMark :size="28" label="S" />
      <div class="sidebar__brand-text">
        <p class="sidebar__brand-name">SAVI</p>
        <p class="sidebar__brand-sub">SEO ERP</p>
      </div>
      <button
        v-if="mobile"
        type="button"
        class="sidebar__close"
        aria-label="Cerrar menú"
        @click="emit('close')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </header>

    <div class="sidebar__action">
      <button type="button" class="sidebar__new" @click="emit('new-chat')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        Nueva conversación
      </button>
    </div>

    <nav class="sidebar__list" aria-label="Conversaciones">
      <p class="sidebar__section">Conversaciones</p>
      <p v-if="loading" class="sidebar__hint">Cargando…</p>
      <p v-else-if="conversations.length === 0" class="sidebar__hint">
        Aún no hay conversaciones.
      </p>
      <ConversationItem
        v-for="c in conversations"
        :key="c.id"
        :conversation="c"
        :active="c.id === activeId"
        @select="emit('select', c.id)"
        @rename="(title) => emit('rename', c.id, title)"
      />
    </nav>

    <footer class="sidebar__footer">
      <ThemeToggle />
    </footer>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--surface-sidebar);
  border-right: 1px solid var(--border);
}

.sidebar--mobile {
  position: fixed;
  inset: 0 auto 0 0;
  width: min(85vw, 320px);
  z-index: 50;
  transform: translateX(-100%);
  transition: transform var(--duration-slow) var(--ease-out);
  box-shadow: var(--shadow-lg);
}

.sidebar--mobile.sidebar--open {
  transform: translateX(0);
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  animation: backdrop-in var(--duration-slow) var(--ease-out);
}

@keyframes backdrop-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.sidebar__brand {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-5) var(--space-4);
  flex-shrink: 0;
}

.sidebar__brand-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}

.sidebar__brand-name {
  margin: 0;
  font-family: var(--font-display);
  font-weight: var(--fw-semibold);
  font-size: 14px;
  letter-spacing: 0.02em;
  color: var(--text);
  line-height: 1.1;
}

.sidebar__brand-sub {
  margin: 0;
  font-size: 10.5px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-subtle);
}

.sidebar__close {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.sidebar__close:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.sidebar__action {
  padding: 0 var(--space-4) var(--space-4);
  flex-shrink: 0;
}

.sidebar__new {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.005em;
  cursor: pointer;
  box-shadow: var(--shadow-xs);
  transition: all var(--duration-fast) var(--ease-out);
}

.sidebar__new:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
  transform: translateY(-0.5px);
  box-shadow: var(--shadow-sm);
}

.sidebar__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar__section {
  margin: var(--space-3) var(--space-4) var(--space-2);
  font-size: 10.5px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-subtle);
}

.sidebar__hint {
  margin: var(--space-2) var(--space-4);
  font-size: 12px;
  color: var(--text-subtle);
}

.sidebar__footer {
  padding: var(--space-3);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
</style>
