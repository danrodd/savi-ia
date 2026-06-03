<script setup lang="ts">
/**
 * UsageView — shell del consumo. Una sola vista con tabs:
 *  - Mi consumo (todos)
 *  - Global (admin)
 *  - KPIs y tarifa (admin)
 *
 * El selector de rango es ÚNICO y compartido por las tres tabs. Cada
 * panel se monta lazy (v-if) y carga sus datos solo al activarse su tab;
 * el store los conserva, así que volver a una tab no re-pega al backend.
 */
import { computed, ref } from 'vue'

import { useRouter } from 'vue-router'

import { useAuthStore } from '@/modules/auth/stores/authStore'
import { type RangeDays, useUsageStore } from '@/modules/usage'
import KpisPanel from '../components/KpisPanel.vue'
import MyUsagePanel from '../components/MyUsagePanel.vue'
import SystemUsagePanel from '../components/SystemUsagePanel.vue'
import { formatCop } from '../utils/format'

type Tab = 'mine' | 'system' | 'kpis'

const router = useRouter()
const authStore = useAuthStore()
const store = useUsageStore()

const tab = ref<Tab>('mine')
const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const rate = computed(() => store.usdToCopRate)

const TABS = computed<{ value: Tab; label: string }[]>(() => {
  const tabs: { value: Tab; label: string }[] = [{ value: 'mine', label: 'Mi consumo' }]
  if (isAdmin.value) {
    tabs.push({ value: 'system', label: 'Global' }, { value: 'kpis', label: 'KPIs y tarifa' })
  }
  return tabs
})

const RANGES: { value: RangeDays; label: string }[] = [
  { value: 7, label: '7 días' },
  { value: 30, label: '30 días' },
  { value: 90, label: '90 días' },
]

function selectTab(next: Tab): void {
  tab.value = next
}

async function onRange(days: RangeDays): Promise<void> {
  await store.setRange(days)
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else void router.push({ name: 'home' })
}
</script>

<template>
  <div class="usage">
    <div class="usage__container">
      <button type="button" class="usage__back" aria-label="Volver" @click="goBack">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Volver
      </button>

      <header class="usage__header">
        <h1 class="usage__title">Consumo</h1>
        <p class="usage__subtitle">
          Tokens y costo de las interacciones con SAVI. El costo se calcula
          en dólares y se muestra convertido a pesos.
        </p>
      </header>

      <div class="usage__controls">
        <div class="usage__tabs" role="tablist">
          <button
            v-for="t in TABS"
            :key="t.value"
            type="button"
            role="tab"
            class="usage__tab"
            :class="{ 'usage__tab--active': tab === t.value }"
            :aria-selected="tab === t.value"
            @click="selectTab(t.value)"
          >
            {{ t.label }}
          </button>
        </div>

        <div class="usage__ranges" aria-label="Rango de tiempo">
          <button
            v-for="r in RANGES"
            :key="r.value"
            type="button"
            class="usage__range"
            :class="{ 'usage__range--active': store.rangeDays === r.value }"
            @click="onRange(r.value)"
          >
            {{ r.label }}
          </button>
        </div>
      </div>

      <MyUsagePanel v-if="tab === 'mine'" />
      <SystemUsagePanel v-else-if="tab === 'system'" />
      <KpisPanel v-else />

      <p class="usage__rate-note">
        Conversión a la tasa de {{ formatCop(1, rate) }} por USD (configurable
        por el administrador). El dato fuente del costo es siempre en dólares.
      </p>
    </div>
  </div>
</template>

<style scoped>
.usage {
  /* El layout global fija `body { overflow: hidden }` (shell del chat), así
     que el scroll de página está deshabilitado. Esta vista debe scrollear
     internamente: ocupa el alto del #app y desborda en su propio eje. */
  height: 100%;
  overflow-y: auto;
  background: var(--bg);
  padding: var(--space-6);
}

.usage__container {
  width: min(1000px, 100%);
  margin: 0 auto;
}

.usage__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  margin-bottom: var(--space-5);
}

.usage__back:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.usage__header {
  margin-bottom: var(--space-6);
}

.usage__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.usage__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 56ch;
  line-height: 1.5;
}

.usage__controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}

.usage__tabs,
.usage__ranges {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.usage__tab,
.usage__range {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.usage__tab:hover,
.usage__range:hover {
  color: var(--text);
}

.usage__tab--active,
.usage__range--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.usage__rate-note {
  margin: var(--space-6) 0 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.5;
}
</style>
