<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { roleLabel } from '@/lib/format'
import type { Permission } from '@/lib/types'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const router = useRouter()

interface NavItem {
  to: string
  label: string
  permission: Permission
}

const NAV: NavItem[] = [
  { to: '/', label: 'Resumen', permission: 'overview.read' },
  { to: '/clientes', label: 'Clientes', permission: 'clients.read' },
  { to: '/instancias', label: 'Instancias', permission: 'instances.read' },
  { to: '/alertas', label: 'Alertas', permission: 'alerts.read' },
  { to: '/configuracion/alertas', label: 'Reglas de alerta', permission: 'alerts.configure' },
  { to: '/staff', label: 'Equipo', permission: 'staff.manage' },
  { to: '/auditoria', label: 'Auditoría', permission: 'audit.read' },
]

const items = computed(() => NAV.filter((item) => auth.can(item.permission)))

async function logout(): Promise<void> {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand">SAVI <span>Cloud</span></div>
      <nav aria-label="Principal">
        <RouterLink v-for="item in items" :key="item.to" :to="item.to" class="link">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <div class="main">
      <header class="top">
        <span class="muted">
          {{ auth.user?.full_name }} · {{ auth.user ? roleLabel(auth.user.role) : '' }}
        </span>
        <button class="btn btn-small" type="button" @click="logout">Salir</button>
      </header>
      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}
.side {
  padding: 1rem 0.8rem;
  border-right: 1px solid var(--border);
  background: var(--surface);
}
.brand {
  padding: 0.2rem 0.6rem 1rem;
  font-size: 1.15rem;
  font-weight: 700;
}
.brand span {
  color: var(--accent);
}
nav {
  display: grid;
  gap: 0.15rem;
}
.link {
  padding: 0.5rem 0.7rem;
  border-radius: 8px;
  color: var(--text);
}
.link:hover {
  background: var(--surface-2);
  text-decoration: none;
}
.link.router-link-exact-active {
  background: var(--surface-2);
  font-weight: 600;
  box-shadow: inset 3px 0 0 var(--accent);
}
.main {
  display: grid;
  grid-template-rows: auto 1fr;
  min-width: 0;
}
.top {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.8rem;
  padding: 0.6rem 1.2rem;
  border-bottom: 1px solid var(--border);
}
.content {
  padding: 1.2rem;
  min-width: 0;
}
@media (max-width: 760px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .side {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  nav {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    overflow-x: auto;
  }
}
</style>
