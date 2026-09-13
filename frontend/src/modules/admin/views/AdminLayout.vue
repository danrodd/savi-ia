<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

const NAV = [
  { to: { name: 'admin-databases' }, label: 'Bases de datos' },
  { to: { name: 'admin-usage' }, label: 'Consumo' },
] as const
</script>

<template>
  <div class="admin">
    <aside class="admin__nav" aria-label="Administración">
      <RouterLink :to="{ name: 'home' }" class="admin__back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Volver al chat
      </RouterLink>
      <p class="admin__section">Administración</p>
      <RouterLink
        v-for="item in NAV"
        :key="item.label"
        :to="item.to"
        class="admin__link"
        active-class="admin__link--active"
      >
        {{ item.label }}
      </RouterLink>
    </aside>

    <main class="admin__main">
      <div class="admin__container">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.admin {
  display: flex;
  height: 100%;
  background: var(--bg);
}

.admin__nav {
  width: var(--sidebar-width, 260px);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-5) var(--space-3);
  background: var(--surface-sidebar);
  border-right: 1px solid var(--border);
}

.admin__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: var(--fw-medium);
  text-decoration: none;
}

.admin__back:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.admin__section {
  margin: 0 0 var(--space-2);
  padding: 0 var(--space-3);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.admin__link {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 13px;
  font-weight: var(--fw-medium);
  text-decoration: none;
}

.admin__link:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.admin__link--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.admin__main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: var(--space-6);
}

.admin__container {
  width: min(1100px, 100%);
  margin: 0 auto;
}

@media (max-width: 768px) {
  .admin {
    flex-direction: column;
  }

  .admin__nav {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    padding: var(--space-3);
    border-right: none;
    border-bottom: 1px solid var(--border);
  }

  .admin__back {
    margin-bottom: 0;
  }

  .admin__section {
    display: none;
  }
}
</style>
