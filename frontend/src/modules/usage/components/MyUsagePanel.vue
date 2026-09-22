<script setup lang="ts">
/**
 * Panel "Mi consumo" — total + costo por respuesta + desglose por
 * proveedor (expandible a modelo) + serie diaria apilada por proveedor.
 * Se carga solo (con guarda) al montarse, o sea cuando su tab se activa
 * por primera vez.
 */
import { computed, onMounted } from 'vue'

import { useUsageStore } from '../stores/usageStore'
import { formatCop, formatTokens, formatUsd } from '../utils/format'
import ProviderBreakdown from './ProviderBreakdown.vue'
import ProviderDailyChart from './ProviderDailyChart.vue'

const store = useUsageStore()
const rate = computed(() => store.usdToCopRate)

const costPerResponseUsd = computed(() => {
  const t = store.mine?.totals
  if (!t || t.message_count === 0) return 0
  return t.cost_usd / t.message_count
})

onMounted(() => {
  if (!store.mine && !store.loadingMine) void store.loadMine()
})
</script>

<template>
  <section class="mu" aria-label="Mi consumo">
    <p v-if="store.loadingMine && !store.mine" class="mu__hint">Cargando…</p>
    <p v-else-if="store.errorMine" class="mu__error" role="alert">{{ store.errorMine }}</p>
    <template v-else-if="store.mine">
      <div class="mu__cards">
        <article class="mu__card mu__card--primary">
          <p class="mu__card-label">Costo total</p>
          <p class="mu__card-value">{{ formatCop(store.mine.totals.cost_usd, rate) }}</p>
          <p class="mu__card-foot">{{ formatUsd(store.mine.totals.cost_usd) }} USD</p>
        </article>
        <article class="mu__card">
          <p class="mu__card-label">Tokens totales</p>
          <p class="mu__card-value">{{ formatTokens(store.mine.totals.total_tokens) }}</p>
          <p class="mu__card-foot">
            {{ formatTokens(store.mine.totals.message_count) }} respuestas
          </p>
        </article>
        <article class="mu__card">
          <p class="mu__card-label">Costo por respuesta</p>
          <p class="mu__card-value">{{ formatCop(costPerResponseUsd, rate) }}</p>
          <p class="mu__card-foot">{{ formatUsd(costPerResponseUsd) }} USD</p>
        </article>
      </div>

      <div class="mu__tokens">
        <div class="mu__token">
          <span class="mu__token-label">Entrada</span>
          <span class="mu__token-value">{{ formatTokens(store.mine.totals.input_tokens) }}</span>
        </div>
        <div class="mu__token">
          <span class="mu__token-label">Salida</span>
          <span class="mu__token-value">{{ formatTokens(store.mine.totals.output_tokens) }}</span>
        </div>
        <div class="mu__token">
          <span class="mu__token-label">Caché (lectura)</span>
          <span class="mu__token-value">
            {{ formatTokens(store.mine.totals.cache_read_input_tokens) }}
          </span>
        </div>
        <div class="mu__token">
          <span class="mu__token-label">Caché (escritura)</span>
          <span class="mu__token-value">
            {{ formatTokens(store.mine.totals.cache_creation_input_tokens) }}
          </span>
        </div>
      </div>

      <section class="mu__section" aria-label="Consumo por proveedor">
        <h2 class="mu__section-title">Por proveedor</h2>
        <ProviderBreakdown :rows="store.mine.per_provider" :rate="rate" />
      </section>

      <section v-if="store.mine.daily_by_provider.length > 0" class="mu__section" aria-label="Consumo por día">
        <h2 class="mu__section-title">Por día</h2>
        <ProviderDailyChart :daily="store.mine.daily_by_provider" :rate="rate" />
      </section>
    </template>
  </section>
</template>

<style scoped>
.mu__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.mu__card {
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-xs);
}

.mu__card--primary {
  background: var(--surface-elev);
  border-color: var(--border-strong, var(--border));
}

.mu__card-label {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.mu__card-value {
  margin: 0;
  font-family: var(--font-display, var(--font-sans));
  font-size: 26px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.mu__card-foot {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.mu__tokens {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow: hidden;
  margin-bottom: var(--space-6);
}

.mu__token {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-elev);
}

.mu__token-label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.mu__token-value {
  font-size: 15px;
  font-weight: var(--fw-medium);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.mu__section {
  margin-bottom: var(--space-6);
}

.mu__section-title {
  margin: 0 0 var(--space-3);
  font-size: 12px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.mu__hint {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--text-subtle);
}

.mu__error {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}
</style>
