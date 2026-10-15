<script setup lang="ts">
import { type ThemeMode, useTheme } from '@savi/ui'
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
import { type Component, computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { roleLabel } from '@/lib/format'
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
      <span class="topbar__brand"><span class="mark" aria-hidden="true">S</span>SAVI Cloud</span>
    </header>

    <div v-if="menuOpen" class="scrim" aria-hidden="true" @click="menuOpen = false" />

    <aside id="console-nav" class="side" :class="{ 'side--open': menuOpen }">
      <div class="identity">
        <span class="mark" aria-hidden="true">S</span>
        <div>
          <strong>SAVI Cloud</strong>
          <small>Consola del staff</small>
        </div>
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
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  color: var(--text-on-brand);
  background: var(--brand-solid);
  font-family: var(--font-display);
  font-weight: var(--fw-bold);
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
    font-size: 13px;
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
