<script setup lang="ts">
import { computed, ref } from 'vue'

import { formatCop, KpisPanel, SystemUsagePanel, UsageRangeSelector, useUsageStore } from '@/modules/usage'

type Tab = 'system' | 'kpis'

const TABS: { value: Tab; label: string }[] = [
  { value: 'system', label: 'Global' },
  { value: 'kpis', label: 'KPIs y tarifa' },
]

const store = useUsageStore()
const tab = ref<Tab>('system')
const rate = computed(() => store.usdToCopRate)
const providerOptions = [
  { value: undefined, label: 'Todos los proveedores' },
  { value: 'claude' as const, label: 'Claude' },
  { value: 'gemini' as const, label: 'Gemini' },
  { value: 'openai' as const, label: 'OpenAI' },
]
</script>

<template>
  <section>
    <header class="ausage__header">
      <h1 class="ausage__title">Consumo global</h1>
      <p class="ausage__subtitle">
        Tokens y costo de todas las interacciones con SAVI. El costo se calcula en dólares y se
        muestra convertido a pesos.
      </p>
    </header>

    <div class="ausage__controls">
      <div class="ausage__tabs" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.value"
          type="button"
          role="tab"
          class="ausage__tab"
          :class="{ 'ausage__tab--active': tab === t.value }"
          :aria-selected="tab === t.value"
          @click="tab = t.value"
        >
          {{ t.label }}
        </button>
      </div>
      <label class="ausage__filter">Proveedor<select :value="store.provider ?? ''" @change="store.setProvider(($event.target as HTMLSelectElement).value === '' ? undefined : (($event.target as HTMLSelectElement).value as 'claude' | 'gemini' | 'openai'))"><option v-for="option in providerOptions" :key="option.label" :value="option.value ?? ''">{{ option.label }}</option></select></label>
      <UsageRangeSelector />
    </div>

    <SystemUsagePanel v-if="tab === 'system'" />
    <KpisPanel v-else />

    <p class="ausage__rate-note">
      Conversión a la tasa de {{ formatCop(1, rate) }} por USD (configurable por el administrador).
      El dato fuente del costo es siempre en dólares.
    </p>
  </section>
</template>

<style scoped>
.ausage__header {
  margin-bottom: var(--space-6);
}

.ausage__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.ausage__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 56ch;
  line-height: 1.5;
}

.ausage__controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}

.ausage__filter { display: inline-flex; align-items: center; gap: var(--space-2); color: var(--text-muted); font-size: 12px; font-weight: var(--fw-medium); }
.ausage__filter select { min-height: 34px; padding: 0 var(--space-6) 0 var(--space-3); color: var(--text); background: var(--surface-elev); border: 1px solid var(--border); border-radius: var(--r-md); font: inherit; }
.ausage__filter select:focus-visible { outline: var(--focus-ring); border-color: var(--brand); }

.ausage__tabs {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.ausage__tab {
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

.ausage__tab:hover {
  color: var(--text);
}

.ausage__tab--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.ausage__rate-note {
  margin: var(--space-6) 0 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.5;
}

@media (max-width: 620px) {
  .ausage__controls { align-items: stretch; }
  .ausage__tabs, .ausage__filter, .ausage__controls :deep(.ranges) { width: 100%; }
  .ausage__filter { justify-content: space-between; }
  .ausage__filter select { flex: 1; }
}
</style>
