<script setup lang="ts">
/**
 * Simulador de tarifa.
 *
 * Toma el costo real por conversación medido (promedio o p95) y proyecta
 * el gasto para un escenario de N clientes × M usuarios × K conversaciones
 * al mes, sugiriendo un piso de tarifa con margen. Todo en COP.
 *
 * Recomendación de negocio: simular sobre el p95, no el promedio. El
 * promedio lo distorsiona el usuario pesado; el p95 cubre al 95% de los
 * casos y te protege el margen.
 */
import { computed, ref } from 'vue'

import type { UsageKpis } from '../types'
import { formatCopAmount, formatUsd } from '../utils/format'

const props = defineProps<{ kpis: UsageKpis; rate: number }>()

type Basis = 'avg' | 'p95'

const clients = ref(10)
const usersPerClient = ref(5)
const convsPerUser = ref(40)
const basis = ref<Basis>('p95')
const margin = ref(3)

const baseCostUsd = computed(() =>
  basis.value === 'p95'
    ? props.kpis.conversations.p95_cost_usd
    : props.kpis.conversations.avg_cost_usd,
)

const convsPerMonth = computed(() => clients.value * usersPerClient.value * convsPerUser.value)
const projectedCostCop = computed(() => convsPerMonth.value * baseCostUsd.value * props.rate)
const costPerClientCop = computed(
  () => usersPerClient.value * convsPerUser.value * baseCostUsd.value * props.rate,
)
const tariffPerClientCop = computed(() => costPerClientCop.value * margin.value)
const pricePerUserCop = computed(() =>
  usersPerClient.value > 0 ? tariffPerClientCop.value / usersPerClient.value : 0,
)
</script>

<template>
  <section class="sim" aria-label="Simulador de tarifa">
    <h2 class="sim__title">Simulador de tarifa</h2>
    <p class="sim__hint">
      Proyectá el gasto y un piso de tarifa a partir del costo real medido.
    </p>

    <div class="sim__grid">
      <label class="sim__field">
        <span class="sim__label">Clientes</span>
        <input v-model.number="clients" type="number" min="1" class="sim__input" />
      </label>
      <label class="sim__field">
        <span class="sim__label">Usuarios por cliente</span>
        <input v-model.number="usersPerClient" type="number" min="1" class="sim__input" />
      </label>
      <label class="sim__field">
        <span class="sim__label">Conversaciones por usuario / mes</span>
        <input v-model.number="convsPerUser" type="number" min="1" class="sim__input" />
      </label>
      <label class="sim__field">
        <span class="sim__label">Base de costo</span>
        <select v-model="basis" class="sim__input">
          <option value="p95">p95 (recomendado)</option>
          <option value="avg">Promedio</option>
        </select>
      </label>
      <label class="sim__field">
        <span class="sim__label">Margen (×)</span>
        <input v-model.number="margin" type="number" min="1" step="0.5" class="sim__input" />
      </label>
    </div>

    <p class="sim__basis-note">
      Costo base por conversación: <strong>{{ formatUsd(baseCostUsd) }}</strong>
      · {{ convsPerMonth.toLocaleString('es-CO') }} conversaciones/mes
    </p>

    <div class="sim__results">
      <article class="sim__result">
        <p class="sim__result-label">Costo proyectado / mes</p>
        <p class="sim__result-value">{{ formatCopAmount(projectedCostCop) }}</p>
      </article>
      <article class="sim__result">
        <p class="sim__result-label">Costo por cliente / mes</p>
        <p class="sim__result-value">{{ formatCopAmount(costPerClientCop) }}</p>
      </article>
      <article class="sim__result sim__result--primary">
        <p class="sim__result-label">Tarifa sugerida por cliente / mes</p>
        <p class="sim__result-value">{{ formatCopAmount(tariffPerClientCop) }}</p>
        <p class="sim__result-foot">{{ formatCopAmount(pricePerUserCop) }} por usuario</p>
      </article>
    </div>
  </section>
</template>

<style scoped>
.sim {
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
}

.sim__title {
  margin: 0 0 var(--space-1);
  font-size: 15px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.sim__hint {
  margin: 0 0 var(--space-4);
  font-size: 12px;
  color: var(--text-muted);
}

.sim__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.sim__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sim__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.sim__input {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-elev);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.sim__input:focus-visible {
  outline: 2px solid var(--brand-ring, var(--brand));
  outline-offset: -1px;
}

.sim__basis-note {
  margin: 0 0 var(--space-4);
  font-size: 12px;
  color: var(--text-muted);
}

.sim__results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: var(--space-3);
}

.sim__result {
  padding: var(--space-4);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.sim__result--primary {
  background: var(--brand);
  border-color: var(--brand);
}

.sim__result--primary .sim__result-label,
.sim__result--primary .sim__result-value,
.sim__result--primary .sim__result-foot {
  color: var(--text-on-brand);
}

.sim__result-label {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.sim__result-value {
  margin: 0;
  font-size: 20px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.sim__result-foot {
  margin: var(--space-1) 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
