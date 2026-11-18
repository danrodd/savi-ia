<script setup lang="ts">
import { type ThemeMode, toast, useTheme } from '@savi/ui'
import { onKeyStroke } from '@vueuse/core'
import {
  Bell,
  Building2,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  ScrollText,
  Server,
  SlidersHorizontal,
  Sun,
  Users,
  X,
} from 'lucide-vue-next'
import { type Component, computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import AlertBell from '@/components/AlertBell.vue'
import { freshAlerts, openAlerts, refreshOpenAlerts } from '@/composables/useOpenAlerts'
import { clientPath } from '@/lib/clientRoutes'
import { roleLabel } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'
import { THEME_STORAGE_KEY } from '@/lib/theme'
import type { Permission } from '@/lib/types'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { mode, cycleTheme } = useTheme({ storageKey: THEME_STORAGE_KEY })

interface NavItem {
  to: string
  label: string
  icon: Component
  permission: Permission
  /** La ruta exacta, para que "Resumen" (`/`) no quede activo en todas las pantallas. */
  exact?: boolean
}

const GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Operación',
    items: [
      {
        to: '/',
        label: 'Resumen',
        icon: LayoutDashboard,
        permission: 'overview.read',
        exact: true,
      },
      { to: '/clientes', label: 'Clientes', icon: Building2, permission: 'clients.read' },
      { to: '/instancias', label: 'Instancias', icon: Server, permission: 'instances.read' },
      { to: '/alertas', label: 'Alertas', icon: Bell, permission: 'alerts.read' },
    ],
  },
  {
    label: 'Administración',
    items: [
      {
        to: '/configuracion/alertas',
        label: 'Reglas de alerta',
        icon: SlidersHorizontal,
        permission: 'alerts.configure',
      },
      { to: '/staff', label: 'Equipo', icon: Users, permission: 'staff.manage' },
      { to: '/auditoria', label: 'Auditoría', icon: ScrollText, permission: 'audit.read' },
    ],
  },
]

const groups = computed(() =>
  GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => auth.can(item.permission)),
  })).filter((group) => group.items.length > 0),
)

// Alertas abiertas (contador, campana y avisos): solo con permiso de verlas. Se releen al
// navegar y cada 30 s, y no mientras la pestaña del navegador está oculta.
const ALERTS_POLL_MS = 30_000
const showAlertBadge = computed(() => auth.can('alerts.read'))
let pollTimer: ReturnType<typeof setInterval> | undefined

function pollAlerts(): void {
  if (showAlertBadge.value && !document.hidden) void refreshOpenAlerts()
}

onMounted(() => {
  pollAlerts()
  pollTimer = setInterval(pollAlerts, ALERTS_POLL_MS)
  document.addEventListener('visibilitychange', pollAlerts)
})
onBeforeUnmount(() => {
  clearInterval(pollTimer)
  document.removeEventListener('visibilitychange', pollAlerts)
})
watch(() => route.path, pollAlerts)

// Aviso dentro de la consola cuando aparece una alerta nueva. Las informativas solo suman al
// contador; las críticas quedan a la vista hasta que la persona las cierre.
const ruleTitle = useRuleTitles()
watch(freshAlerts, (alerts) => {
  for (const alert of alerts) {
    if (alert.severity === 'info') continue
    const notify = alert.severity === 'critical' ? toast.error : toast.warning
    notify(ruleTitle(alert.rule_code), {
      description: alert.client_name ?? undefined,
      duration: alert.severity === 'critical' ? Number.POSITIVE_INFINITY : 10_000,
      action: {
        label: 'Ver',
        onClick: () => void router.push(clientPath(alert.client_id, 'alertas')),
      },
    })
  }
})

// El título de la pestaña lleva el conteo, así se ve aunque la consola esté detrás de otra.
const TITLE_COUNT = /^\(\d+\+?\) /
watch(
  [openAlerts, () => route.fullPath],
  () => {
    const base = document.title.replace(TITLE_COUNT, '')
    const n = showAlertBadge.value ? (openAlerts.value ?? 0) : 0
    document.title = n > 0 ? `(${n > 99 ? '99+' : n}) ${base}` : base
  },
  { flush: 'post' },
)

function badgeFor(item: NavItem): number | null {
  if (item.to !== '/alertas' || !showAlertBadge.value) return null
  return openAlerts.value
}

function isActive(item: NavItem): boolean {
  if (item.exact) return route.path === item.to
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

const THEME: Record<ThemeMode, { icon: Component; label: string }> = {
  light: { icon: Sun, label: 'Tema claro' },
  dark: { icon: Moon, label: 'Tema oscuro' },
  system: { icon: Monitor, label: 'Tema del sistema' },
}
// Un valor guardado desconocido (editado a mano, versión vieja) cae en "sistema" en vez de romper.
const theme = computed(() => THEME[mode.value] ?? THEME.system)

const initials = computed(() => {
  const name = auth.user?.full_name?.trim() ?? ''
  const parts = name.split(/\s+/).filter(Boolean)
  return (
    parts.length > 1 ? `${parts[0]?.[0]}${parts.at(-1)?.[0]}` : name.slice(0, 2)
  ).toUpperCase()
})

// Menú desplegable en pantallas chicas: se cierra al navegar o con Escape.
const menuOpen = ref(false)
watch(
  () => route.fullPath,
  () => (menuOpen.value = false),
)
onKeyStroke('Escape', () => (menuOpen.value = false))

async function logout(): Promise<void> {
  await auth.logout()
  await router.push({ name: 'login' })
}

// Archivo de `public/`: como binding, Vite no intenta resolverlo como import.
const MARK = '/savi-mark.png'
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <button
        type="button"
        class="topbar__menu"
        :aria-expanded="menuOpen"
        aria-controls="console-nav"
        :aria-label="menuOpen ? 'Cerrar menú' : 'Abrir menú'"
        @click="menuOpen = !menuOpen"
      >
        <X v-if="menuOpen" :size="18" aria-hidden="true" />
        <Menu v-else :size="18" aria-hidden="true" />
      </button>
      <span class="topbar__brand"><img class="mark" :src="MARK" alt="" width="28" height="28">SAVI Cloud</span>
      <AlertBell v-if="showAlertBadge" class="topbar__bell" />
    </header>

    <div v-if="menuOpen" class="scrim" aria-hidden="true" @click="menuOpen = false" />

    <aside id="console-nav" class="side" :class="{ 'side--open': menuOpen }">
      <div class="identity">
        <img class="mark" :src="MARK" alt="" width="34" height="34">
        <div>
          <strong>SAVI Cloud</strong>
          <small>Consola del staff</small>
        </div>
        <AlertBell v-if="showAlertBadge" class="identity__bell" />
      </div>

      <nav class="nav" aria-label="Principal">
        <div v-for="group in groups" :key="group.label" class="nav__group">
          <p class="nav__section">{{ group.label }}</p>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            class="nav__link"
            :class="{ 'nav__link--active': isActive(item) }"
            :aria-current="isActive(item) ? 'page' : undefined"
          >
            <component :is="item.icon" :size="16" aria-hidden="true" />
            {{ item.label }}
            <span
              v-if="badgeFor(item)"
              class="nav__badge"
              :data-test="`nav-badge-${item.to.slice(1)}`"
              :aria-label="`${badgeFor(item)} abiertas`"
            >
              {{ (badgeFor(item) ?? 0) > 99 ? '99+' : badgeFor(item) }}
            </span>
          </RouterLink>
        </div>
      </nav>

      <div class="account">
        <div class="account__user">
          <span class="account__avatar" aria-hidden="true">{{ initials }}</span>
          <div class="account__text">
            <strong>{{ auth.user?.full_name }}</strong>
            <small>{{ auth.user ? roleLabel(auth.user.role) : '' }}</small>
          </div>
        </div>
        <div class="account__actions">
          <button
            type="button"
            class="account__button"
            :title="`${theme.label} (cambiar)`"
            :aria-label="`${theme.label}. Cambiar tema`"
            @click="cycleTheme"
          >
            <component :is="theme.icon" :size="16" aria-hidden="true" />
          </button>
          <button type="button" class="account__button" title="Salir" aria-label="Salir" @click="logout">
            <LogOut :size="16" aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>

    <main class="main">
      <div class="container">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.identity__bell {
  margin-left: auto;
}

.topbar__bell {
  margin-left: auto;
}

/* El documento no hace scroll (tokens de SAVI): la barra lateral queda fija y solo se
   desplaza el contenido. */
.shell {
  display: flex;
  height: 100%;
  background: var(--surface);
}

.side {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: var(--sidebar-width, 272px);
  padding: var(--space-5) var(--space-4);
  overflow-y: auto;
  background: var(--surface-sidebar);
  border-right: 1px solid var(--border);
}

.identity {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-2) var(--space-6);
}

.identity div {
  display: grid;
  gap: 1px;
}

.identity strong {
  font-family: var(--font-display);
  letter-spacing: 0.04em;
}

.identity small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.mark {
  display: block;
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  object-fit: cover;
  border-radius: 11px;
  box-shadow: var(--shadow-brand);
}

.nav {
  display: grid;
  gap: var(--space-5);
}

.nav__group {
  display: grid;
  gap: 2px;
}

.nav__section {
  margin: 0 0 var(--space-2);
  padding: 0 var(--space-3);
  font-size: 11px;
  font-weight: var(--fw-medium);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.nav__link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 34px;
  padding: 0 var(--space-3);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 13px;
  font-weight: var(--fw-medium);
  text-decoration: none;
}

.nav__badge {
  margin-left: auto;
  min-width: 20px;
  padding: 0 6px;
  border-radius: var(--r-pill);
  background: var(--danger);
  color: #fff;
  font-size: 11px;
  font-weight: var(--fw-semibold);
  line-height: 20px;
  text-align: center;
}

.nav__link:hover {
  background: var(--surface-subtle);
  color: var(--text);
  text-decoration: none;
}

.nav__link--active,
.nav__link--active:hover {
  background: var(--brand-soft);
  color: var(--brand-strong);
  box-shadow: inset 3px 0 0 var(--brand);
}

.account {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: auto;
  padding: var(--space-4) var(--space-2) 0;
  border-top: 1px solid var(--border);
}

.account__user {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.account__avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--navy-soft);
  color: var(--navy);
  font-size: 12px;
  font-weight: var(--fw-semibold);
}

.account__text {
  display: grid;
  min-width: 0;
}

.account__text strong {
  overflow: hidden;
  font-size: 12.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account__text small {
  color: var(--text-muted);
  font-size: 11px;
}

.account__actions {
  display: flex;
  gap: var(--space-1);
}

.account__button {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.account__button:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: clamp(var(--space-5), 4vw, var(--space-8));
}

.container {
  width: min(1180px, 100%);
  margin: 0 auto;
}

.topbar,
.scrim {
  display: none;
}

@media (max-width: 860px) {
  .shell {
    flex-direction: column;
  }

  /* En el celular la campana va en la barra de arriba, no repetida en el menú. */
  .identity__bell {
    display: none;
  }

  .topbar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-shrink: 0;
    height: 52px;
    padding: 0 var(--space-4);
    background: var(--surface-sidebar);
    border-bottom: 1px solid var(--border);
  }

  .topbar__menu {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    background: var(--surface-elev);
    color: var(--text);
    cursor: pointer;
  }

  .topbar__brand {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    font-family: var(--font-display);
    font-weight: var(--fw-semibold);
  }

  .topbar__brand .mark {
    width: 28px;
    height: 28px;
    border-radius: 9px;
  }

  .scrim {
    display: block;
    position: fixed;
    inset: 52px 0 0;
    z-index: 30;
    background: rgba(0, 0, 0, 0.35);
  }

  .side {
    position: fixed;
    top: 52px;
    bottom: 0;
    left: 0;
    z-index: 40;
    width: min(300px, 86vw);
    transform: translateX(-100%);
    visibility: hidden;
    transition:
      transform var(--duration-normal) var(--ease-out),
      visibility var(--duration-normal);
  }

  .side--open {
    transform: translateX(0);
    visibility: visible;
    box-shadow: var(--shadow-lg);
  }

  .identity {
    display: none;
  }

  .main {
    padding: var(--space-5) var(--space-4);
  }
}
</style>
