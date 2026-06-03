<script setup lang="ts">
import { computed, ref } from 'vue'

import { useRouter } from 'vue-router'

import Tooltip from '@/components/ui/Tooltip.vue'
import { useAuthStore } from '@/modules/auth/stores/authStore'
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
  share: [id: string]
  delete: [id: string]
  'new-chat': []
  close: []
}>()

const authStore = useAuthStore()
const router = useRouter()
const isLoggingOut = ref(false)

const userInitial = computed(() => {
  const fullName = authStore.user?.full_name ?? authStore.user?.login ?? ''
  return fullName.trim().charAt(0).toUpperCase() || 'U'
})

const userDisplayName = computed(() => {
  return authStore.user?.full_name ?? authStore.user?.login ?? 'Invitado'
})

const userSubtitle = computed(() => {
  if (!authStore.user) return ''
  const { login, is_admin } = authStore.user
  return is_admin ? `${login} · Admin` : login
})

async function onLogout(): Promise<void> {
  isLoggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    isLoggingOut.value = false
    void router.push({ name: 'login' })
  }
}

function goToProfile(): void {
  void router.push({ name: 'profile' })
}

function goToUsage(): void {
  void router.push({ name: 'usage' })
}
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
      <Tooltip v-if="mobile" text="Cerrar menú" side="bottom">
        <button type="button" class="sidebar__close" aria-label="Cerrar menú" @click="emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </Tooltip>
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
        @share="emit('share', c.id)"
        @delete="emit('delete', c.id)"
      />
    </nav>

    <footer class="sidebar__footer">
      <button type="button" class="sidebar__nav-link" @click="goToUsage">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
        </svg>
        Consumo
      </button>

      <div v-if="authStore.user" class="sidebar__user" aria-label="Usuario autenticado">
        <Tooltip text="Ver mi perfil" side="top">
          <button
            type="button"
            class="sidebar__user-trigger"
            aria-label="Ver mi perfil"
            @click="goToProfile"
          >
            <div class="sidebar__user-avatar" aria-hidden="true">{{ userInitial }}</div>
            <div class="sidebar__user-meta">
              <p class="sidebar__user-name">{{ userDisplayName }}</p>
              <p v-if="userSubtitle" class="sidebar__user-sub">{{ userSubtitle }}</p>
            </div>
          </button>
        </Tooltip>
        <Tooltip text="Cerrar sesión" side="top">
          <button
            type="button"
            class="sidebar__logout"
            aria-label="Cerrar sesión"
            :disabled="isLoggingOut"
            @click="onLogout"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </Tooltip>
      </div>
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
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sidebar__nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.sidebar__nav-link:hover {
  background: var(--surface-hover);
  color: var(--text);
}

.sidebar__user {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.sidebar__user-trigger {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: 1;
  min-width: 0;
  padding: var(--space-2);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  text-align: left;
  transition: background var(--duration-fast) var(--ease-out);
}

.sidebar__user-trigger:hover {
  background: var(--surface-hover);
}

.sidebar__user-trigger:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: -2px;
}

.sidebar__user-avatar {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  background: var(--brand);
  color: var(--text-on-brand);
  border-radius: 50%;
  font-size: 12px;
  font-weight: var(--fw-semibold);
  flex-shrink: 0;
}

.sidebar__user-meta {
  flex: 1;
  min-width: 0;
}

.sidebar__user-name {
  margin: 0;
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar__user-sub {
  margin: 0;
  font-size: 10.5px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar__logout {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--duration-fast) var(--ease-out);
}

.sidebar__logout:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--text);
}

.sidebar__logout:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
