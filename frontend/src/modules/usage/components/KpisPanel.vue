<script setup lang="ts">
/**
 * Panel "KPIs y tarifa" (admin) — percentiles, proyección, gráficas
 * (distribución, diaria, composición de tokens), simulador de tarifa y
 * export CSV. Carga kpis + conversaciones + system (para la serie diaria
 * y la composición) con guarda al activarse su tab.
 */
import { computed, onMounted } from 'vue'

import { useUsageStore } from '../stores/usageStore'
import { downloadCsv, toCsv } from '../utils/csv'
import { formatCop, formatCopAmount, formatDay, formatTokens, formatUsd } from '../utils/format'
import TariffSimulator from './TariffSimulator.vue'
import UsageChart from './UsageChart.vue'

const store = useUsageStore()
const rate = computed(() => store.usdToCopRate)
const loading = computed(
  () => store.loadingKpis || store.loadingSystem || store.loadingConversations,
)

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function palette(): {
  text: string
  muted: string
  border: string
  brand: string
  series: string[]
} {
  const brand = cssVar('--brand', '#4f46e5')
  return {
    text: cssVar('--text', '#1a1a1a'),
    muted: cssVar('--text-muted', '#6b7280'),
    border: cssVar('--border', '#e5e7eb'),
    brand,
    series: [brand, '#22c55e', '#f59e0b', '#06b6d4'],
  }
}

function cop(usd: number): number {
  return Math.round(usd * rate.value)
}

// Distribución: costo por conversación ordenado ascendente, con líneas en
// promedio / p90 / p95. Muestra el "tail" que justifica tarifar sobre p95.
const distributionOption = computed<Record<string, unknown>>(() => {
  const p = palette()
  const sorted = [...store.conversations].sort((a, b) => a.cost_usd - b.cost_usd)
  const k = store.kpis
  const marks = k
    ? [
        { yAxis: cop(k.conversations.avg_cost_usd), name: 'Prom' },
        { yAxis: cop(k.conversations.p90_cost_usd), name: 'p90' },
        { yAxis: cop(k.conversations.p95_cost_usd), name: 'p95' },
      ]
    : []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 64, right: 16, top: 24, bottom: 24 },
    xAxis: { type: 'category', show: false, data: sorted.map((_, i) => i + 1) },
    yAxis: {
      type: 'value',
      axisLabel: { color: p.muted, formatter: (v: number) => formatCopAmount(v) },
      splitLine: { lineStyle: { color: p.border } },
    },
    series: [
      {
        type: 'line',
        showSymbol: false,
        data: sorted.map((c) => cop(c.cost_usd)),
        lineStyle: { color: p.brand },
        itemStyle: { color: p.brand },
        areaStyle: { opacity: 0.12 },
        markLine: {
          symbol: 'none',
          lineStyle: { type: 'dashed', color: p.muted },
          label: { formatter: '{b}', color: p.muted, fontSize: 10 },
          data: marks,
        },
      },
    ],
  }
})

const dailyOption = computed<Record<string, unknown>>(() => {
  const p = palette()
  const daily = store.system?.daily ?? []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 64, right: 16, top: 16, bottom: 40 },
    xAxis: {
      type: 'category',
      data: daily.map((d) => formatDay(d.day)),
      axisLabel: { color: p.muted },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: p.muted, formatter: (v: number) => formatCopAmount(v) },
      splitLine: { lineStyle: { color: p.border } },
    },
    series: [
      {
        type: 'bar',
        data: daily.map((d) => cop(d.totals.cost_usd)),
        itemStyle: { color: p.brand, borderRadius: [3, 3, 0, 0] },
      },
    ],
  }
})

const tokenOption = computed<Record<string, unknown>>(() => {
  const p = palette()
  const t = store.system?.totals
  if (!t) return {}
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: p.muted } },
    series: [
      {
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '44%'],
        color: p.series,
        label: { color: p.text, fontSize: 11 },
        data: [
          { value: t.input_tokens, name: 'Entrada' },
          { value: t.output_tokens, name: 'Salida' },
          { value: t.cache_read_input_tokens, name: 'Caché lectura' },
          { value: t.cache_creation_input_tokens, name: 'Caché escritura' },
        ],
      },
    ],
  }
})

function userLabel(userId: number | null): string {
  return userId === null ? 'Legado' : `#${userId}`
}

function exportCsv(): void {
  const headers = [
    'conversation_id',
    'user_id',
    'title',
    'turns',
    'total_tokens',
    'cost_usd',
    'cost_cop',
    'last_activity',
  ]
  const rows = store.conversations.map((c) => [
    c.conversation_id,
    c.user_id ?? '',
    c.title,
    c.turns,
    c.total_tokens,
    c.cost_usd.toFixed(6),
    cop(c.cost_usd),
    c.last_activity,
  ])
  const { from, to } = store.dateRange()
  downloadCsv(`consumo-conversaciones-${from}_a_${to}.csv`, toCsv(headers, rows))
}

onMounted(() => {
  if (!store.kpis && !store.loadingKpis) void store.loadKpis()
  if (store.conversations.length === 0 && !store.loadingConversations) {
    void store.loadConversations()
  }
  if (!store.system && !store.loadingSystem) void store.loadSystem()
})
</script>

<template>
  <section class="kp" aria-label="KPIs y tarifa">
    <div class="kp__bar">
      <p class="kp__note">
        Para fijar tarifa mirá los percentiles, no el promedio: unos pocos
        usuarios pesados lo distorsionan. El p95 cubre al 95% de las
        conversaciones y es el piso seguro para no perder margen.
      </p>
      <button
        type="button"
        class="kp__export"
        :disabled="store.conversations.length === 0"
        @click="exportCsv"
      >
        Exportar CSV
      </button>
    </div>

    <p v-if="store.errorKpis" class="kp__error" role="alert">{{ store.errorKpis }}</p>
    <p v-else-if="loading && !store.kpis" class="kp__hint">Cargando KPIs…</p>

    <template v-if="store.kpis">
      <div class="kp__cards">
        <article class="kp__card kp__card--primary">
          <p class="kp__card-label">Proyección mensual</p>
          <p class="kp__card-value">
            {{ formatCop(store.kpis.projected_monthly_cost_usd, rate) }}
          </p>
          <p class="kp__card-foot">al ritmo de los últimos {{ store.kpis.period_days }} días</p>
        </article>
        <article class="kp__card">
          <p class="kp__card-label">Costo prom. / conversación</p>
          <p class="kp__card-value">
            {{ formatCop(store.kpis.conversations.avg_cost_usd, rate) }}
          </p>
          <p class="kp__card-foot">{{ formatUsd(store.kpis.conversations.avg_cost_usd) }} USD</p>
        </article>
        <article class="kp__card kp__card--accent">
          <p class="kp__card-label">p95 / conversación</p>
          <p class="kp__card-value">
            {{ formatCop(store.kpis.conversations.p95_cost_usd, rate) }}
          </p>
          <p class="kp__card-foot">95% cuesta menos que esto</p>
        </article>
        <article class="kp__card">
          <p class="kp__card-label">Costo prom. / turno</p>
          <p class="kp__card-value">{{ formatCop(store.kpis.avg_cost_per_turn_usd, rate) }}</p>
          <p class="kp__card-foot">
            {{ formatTokens(Math.round(store.kpis.avg_tokens_per_turn)) }} tokens/turno
          </p>
        </article>
      </div>

      <div class="kp__cards">
        <article class="kp__mini">
          <span class="kp__mini-label">Conversaciones</span>
          <span class="kp__mini-value">{{ formatTokens(store.kpis.conversations.count) }}</span>
        </article>
        <article class="kp__mini">
          <span class="kp__mini-label">Usuarios activos</span>
          <span class="kp__mini-value">{{ formatTokens(store.kpis.users.active_count) }}</span>
        </article>
        <article class="kp__mini">
          <span class="kp__mini-label">Conv. prom. / usuario</span>
          <span class="kp__mini-value">{{ store.kpis.users.avg_conversations.toFixed(1) }}</span>
        </article>
        <article class="kp__mini">
          <span class="kp__mini-label">Ratio de caché</span>
          <span class="kp__mini-value">{{ (store.kpis.cache_read_ratio * 100).toFixed(0) }}%</span>
        </article>
      </div>

      <div class="kp__charts">
        <section class="kp__chart-box">
          <h2 class="kp__chart-title">Distribución de costo por conversación</h2>
          <UsageChart :option="distributionOption" :height="320" />
        </section>
        <section class="kp__chart-box">
          <h2 class="kp__chart-title">Composición de tokens</h2>
          <UsageChart :option="tokenOption" :height="300" />
        </section>
        <section class="kp__chart-box">
          <h2 class="kp__chart-title">Costo por día</h2>
          <UsageChart :option="dailyOption" :height="280" />
        </section>
      </div>

      <TariffSimulator :kpis="store.kpis" :rate="rate" />

      <section class="kp__table-box" aria-label="Conversaciones más pesadas">
        <h2 class="kp__chart-title">Conversaciones más pesadas</h2>
        <p v-if="store.conversations.length === 0" class="kp__hint">
          Sin conversaciones en este período.
        </p>
        <table v-else class="kp__table">
          <thead>
            <tr>
              <th scope="col">Conversación</th>
              <th scope="col">Usuario</th>
              <th scope="col" class="kp__num">Turnos</th>
              <th scope="col" class="kp__num">Tokens</th>
              <th scope="col" class="kp__num">Costo</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in store.conversations.slice(0, 20)" :key="c.conversation_id">
              <td class="kp__title-cell">{{ c.title }}</td>
              <td>{{ userLabel(c.user_id) }}</td>
              <td class="kp__num">{{ formatTokens(c.turns) }}</td>
              <td class="kp__num">{{ formatTokens(c.total_tokens) }}</td>
              <td class="kp__num kp__num--strong">{{ formatCop(c.cost_usd, rate) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="store.conversations.length > 20" class="kp__hint">
          Mostrando las 20 más caras de {{ store.conversations.length }}. El CSV
          trae el detalle completo.
        </p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.kp__bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
}

.kp__note {
  flex: 1;
  min-width: 240px;
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}

.kp__export {
  padding: var(--space-2) var(--space-4);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.kp__export:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: var(--border-strong, var(--border));
}

.kp__export:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.kp__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.kp__card {
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-xs);
}

.kp__card--primary {
  background: var(--surface-elev);
  border-color: var(--border-strong, var(--border));
}

.kp__card--accent {
  border-color: var(--brand);
}

.kp__card-label {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: var(--fw-medium);
}

.kp__card-value {
  margin: 0;
  font-family: var(--font-display, var(--font-sans));
  font-size: 22px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.kp__card-foot {
  margin: var(--space-2) 0 0;
  font-size: 11px;
  color: var(--text-muted);
}

.kp__mini {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.kp__mini-label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.kp__mini-value {
  font-size: 16px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.kp__charts {
  /* Cada gráfica en su sección, apiladas full-width. Con altura fija por
     gráfica (prop height) el alto es predecible y el scroll funciona. */
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.kp__chart-box {
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
}

.kp__chart-title {
  margin: 0 0 var(--space-3);
  font-size: 12px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: var(--fw-medium);
}

.kp__table-box {
  margin-top: var(--space-5);
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
}

.kp__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.kp__table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: var(--fw-medium);
  border-bottom: 1px solid var(--border);
}

.kp__table td {
  padding: var(--space-3);
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.kp__title-cell {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kp__num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.kp__num--strong {
  font-weight: var(--fw-semibold);
}

.kp__hint {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--text-subtle);
}

.kp__error {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}
</style>
