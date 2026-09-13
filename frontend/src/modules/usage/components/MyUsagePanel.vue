<script setup lang="ts">
/**
 * Panel "Mi consumo" — total + desglose de tokens + serie diaria del
 * usuario autenticado. Se carga solo (con guarda) al montarse, o sea
 * cuando su tab se activa por primera vez.
 */
import { computed, onMounted } from 'vue'

import { useUsageStore } from '../stores/usageStore'
import { formatCop, formatDay, formatTokens, formatUsd } from '../utils/format'

const store = useUsageStore()
const rate = computed(() => store.usdToCopRate)

const dailyMax = computed(() =>
  (store.mine?.daily ?? []).reduce((max, d) => Math.max(max, d.totals.cost_usd), 0),
)

function barWidth(costUsd: number): string {
  if (dailyMax.value <= 0) return '0%'
  return `${Math.max(2, (costUsd / dailyMax.value) * 100)}%`
}

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

      <section class="mu__daily" aria-label="Consumo por día">
        <h2 class="mu__section-title">Por día</h2>
        <p v-if="store.mine.daily.length === 0" class="mu__hint">
          Sin consumo en este período.
        </p>
        <ul v-else class="mu__day-list">
          <li v-for="d in store.mine.daily" :key="d.day" class="mu__day">
            <span class="mu__day-date">{{ formatDay(d.day) }}</span>
            <span class="mu__day-bar-track">
              <span class="mu__day-bar" :style="{ width: barWidth(d.totals.cost_usd) }" />
            </span>
            <span class="mu__day-cost">{{ formatCop(d.totals.cost_usd, rate) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.mu__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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

.mu__section-title {
  margin: 0 0 var(--space-3);
  font-size: 12px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.mu__day-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mu__day {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  align-items: center;
  gap: var(--space-3);
}

.mu__day-date {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.mu__day-bar-track {
  height: 8px;
  background: var(--surface-subtle);
  border-radius: 999px;
  overflow: hidden;
}

.mu__day-bar {
  display: block;
  height: 100%;
  background: var(--brand);
  border-radius: 999px;
  transition: width var(--duration-slow) var(--ease-out);
}

.mu__day-cost {
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text);
  font-variant-numeric: tabular-nums;
  text-align: right;
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
