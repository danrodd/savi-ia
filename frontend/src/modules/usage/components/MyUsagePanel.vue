<script setup lang="ts">
/**
 * Panel "Mi consumo".
 *
 * Una persona de soporte sólo necesita saber cuántas consultas hizo: ve ese
 * número y su evolución por día. Tokens, caché, costos en USD/COP y el
 * desglose por proveedor son datos de administración y quedan para quien es
 * admin: total + costo por respuesta + desglose por proveedor (expandible a
 * modelo) + serie diaria apilada por proveedor.
 * Se carga solo (con guarda) al montarse, o sea cuando su tab se activa
 * por primera vez.
 */
import { computed, onMounted } from 'vue'

import { useAuthStore } from '@/modules/auth/stores/authStore'
import { useUsageStore } from '../stores/usageStore'
import { formatCop, formatDay, formatTokens, formatUsd } from '../utils/format'
import { dailyQueryBars, periodDescription } from '../utils/simpleUsage'
import ProviderBreakdown from './ProviderBreakdown.vue'
import ProviderDailyChart from './ProviderDailyChart.vue'

const store = useUsageStore()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.is_admin === true)
const rate = computed(() => store.usdToCopRate)

const queryCount = computed(() => store.mine?.totals.message_count ?? 0)
const bars = computed(() => dailyQueryBars(store.mine?.daily ?? []))
// Con pocos días cada barra lleva su número y su fecha; con muchos, solo el
// recorrido y las fechas de los extremos.
const dense = computed(() => bars.value.length > 14)

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
    <template v-else-if="store.mine && !isAdmin">
      <div class="mu__cards">
        <article class="mu__card mu__card--primary">
          <p class="mu__card-label">Consultas realizadas</p>
          <p class="mu__card-value">{{ formatTokens(queryCount) }}</p>
          <p class="mu__card-foot">{{ periodDescription(store.preset) }}</p>
        </article>
      </div>

      <p v-if="queryCount === 0" class="mu__hint">
        Todavía no hiciste consultas en este período.
      </p>
      <section v-else-if="bars.length > 1" class="mu__section" aria-label="Consultas por día">
        <h2 class="mu__section-title">Consultas por día</h2>
        <ul class="mu__bars" :class="{ 'mu__bars--dense': dense }">
          <li
            v-for="b in bars"
            :key="b.day"
            class="mu__bar"
            :title="`${formatDay(b.day)}: ${b.count} ${b.count === 1 ? 'consulta' : 'consultas'}`"
          >
            <span v-if="!dense" class="mu__bar-count">{{ b.count }}</span>
            <span class="mu__bar-track">
              <span class="mu__bar-fill" :style="{ height: `${b.percent}%` }" />
            </span>
            <span v-if="!dense" class="mu__bar-day">{{ formatDay(b.day) }}</span>
          </li>
        </ul>
        <div v-if="dense" class="mu__bars-axis">
          <span>{{ formatDay(bars[0]?.day ?? '') }}</span>
          <span>{{ formatDay(bars[bars.length - 1]?.day ?? '') }}</span>
        </div>
      </section>
    </template>
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

.mu__bars {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-4);
  list-style: none;
  overflow-x: auto;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.mu__bars--dense {
  gap: 3px;
}

.mu__bar {
  flex: 0 1 64px;
  min-width: 2px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
}

.mu__bars--dense .mu__bar {
  flex: 1 1 0;
}

.mu__bar-track {
  display: flex;
  align-items: flex-end;
  width: 100%;
  height: 72px;
}

.mu__bars:not(.mu__bars--dense) .mu__bar-track {
  width: 32px;
}

.mu__bar-fill {
  display: block;
  width: 100%;
  min-height: 2px;
  background: var(--brand);
  border-radius: 3px 3px 0 0;
  opacity: 0.85;
}

.mu__bar-count {
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.mu__bar-day {
  font-size: 11px;
  color: var(--text-subtle);
  white-space: nowrap;
}

.mu__bars-axis {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-2);
  font-size: 11px;
  color: var(--text-subtle);
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
