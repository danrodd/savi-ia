<script setup lang="ts">
import { Alert, Button, Card, DataTable, type TableColumn } from '@savi/ui'
import { Activity, AlertTriangle, Clock, DollarSign, TrendingUp, Users } from 'lucide-vue-next'
import { computed, watch } from 'vue'
import BarChart from '@/components/BarChart.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import KpiCard from '@/components/KpiCard.vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { formatDay, formatInt, formatMs, formatPercent, formatUsd } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const { id } = useClientContext()
const metrics = useAsync(() => consoleApi.clientMetrics(id.value))
watch(id, () => metrics.reload())

const series = computed(() =>
  (metrics.data.value?.series ?? []).map((d) => ({
    label: formatDay(d.day).slice(0, 5),
    value: d.turns,
  })),
)

const MODEL_COLUMNS: TableColumn[] = [
  { key: 'provider', label: 'Proveedor' },
  { key: 'model', label: 'Modelo' },
  { key: 'turns', label: 'Turnos', align: 'right' },
  { key: 'tokens', label: 'Tokens', align: 'right' },
  { key: 'cost_usd', label: 'Costo', align: 'right' },
]

const TOOL_COLUMNS: TableColumn[] = [
  { key: 'name', label: 'Herramienta' },
  { key: 'tipo', label: 'Tipo' },
  { key: 'uses', label: 'Usos', align: 'right' },
  { key: 'errors', label: 'Con error', align: 'right' },
]

const models = computed(() =>
  (metrics.data.value?.by_model ?? []).map((m) => ({ ...m, key: `${m.provider}-${m.model}` })),
)
const tools = computed(() =>
  (metrics.data.value?.tools ?? []).map((t) => ({ ...t, key: `${t.name}-${t.tipo}` })),
)
</script>

<template>
  <div class="stack">
    <Alert v-if="metrics.error.value" tone="danger">
      {{ metrics.error.value }}
      <template #action>
        <Button size="sm" variant="secondary" @click="metrics.reload()">Reintentar</Button>
      </template>
    </Alert>

    <div class="summary__head">
      <p class="muted">Últimos 30 días.</p>
      <FreshnessChip v-if="metrics.data.value" :seconds="metrics.data.value.freshness.seconds" />
    </div>

    <div v-if="metrics.data.value" class="grid-kpi">
      <KpiCard label="Turnos" metric="turns" :icon="Activity" :value="formatInt(metrics.data.value.totals.turns)" />
      <KpiCard
        label="Usuarios activos"
        metric="active_users"
        :icon="Users"
        :value="formatInt(metrics.data.value.totals.active_users)"
        :hint="`${metrics.data.value.totals.entering_users} entran`"
      />
      <KpiCard
        label="Adopción"
        metric="adoption"
        :icon="TrendingUp"
        :value="formatPercent(metrics.data.value.totals.adoption)"
      />
      <KpiCard
        label="Costo"
        metric="cost_usd"
        :icon="DollarSign"
        :value="formatUsd(metrics.data.value.totals.cost_usd)"
        :hint="`${metrics.data.value.totals.turns_without_price} turnos sin precio`"
      />
      <KpiCard
        label="Tasa de error"
        metric="error_rate"
        :icon="AlertTriangle"
        :tone="(metrics.data.value.totals.error_rate ?? 0) > 0.05 ? 'warning' : 'neutral'"
        :value="formatPercent(metrics.data.value.totals.error_rate)"
        :hint="`${metrics.data.value.totals.turns_with_error} con error`"
      />
      <KpiCard
        label="Latencia p50 / p90"
        metric="latency"
        :icon="Clock"
        :value="`${formatMs(metrics.data.value.totals.latency_p50_ms)} / ${formatMs(metrics.data.value.totals.latency_p90_ms)}`"
      />
    </div>

    <Card title="Turnos por día">
      <BarChart :data="series" :format="formatInt" />
    </Card>

    <div class="summary__tables">
      <Card title="Por modelo" padding="none">
        <DataTable
          :columns="MODEL_COLUMNS"
          :rows="models"
          row-key="key"
          :loading="metrics.loading.value"
          empty-text="Sin turnos en el período."
        >
          <template #cell-provider="{ row }">{{ row.provider ?? '—' }}</template>
          <template #cell-model="{ row }">{{ row.model ?? '—' }}</template>
          <template #cell-turns="{ row }"><span class="num">{{ formatInt(row.turns) }}</span></template>
          <template #cell-tokens="{ row }"><span class="num">{{ formatInt(row.tokens) }}</span></template>
          <template #cell-cost_usd="{ row }"><span class="num">{{ formatUsd(row.cost_usd) }}</span></template>
        </DataTable>
      </Card>

      <Card title="Herramientas" padding="none">
        <DataTable
          :columns="TOOL_COLUMNS"
          :rows="tools"
          row-key="key"
          :loading="metrics.loading.value"
          empty-text="Sin uso de herramientas."
        >
          <template #cell-tipo="{ row }">{{ row.tipo ?? '—' }}</template>
          <template #cell-uses="{ row }"><span class="num">{{ formatInt(row.uses) }}</span></template>
          <template #cell-errors="{ row }"><span class="num">{{ formatInt(row.errors) }}</span></template>
        </DataTable>
      </Card>
    </div>
  </div>
</template>

<style scoped>
.summary__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: calc(-1 * var(--space-3));
}

.summary__head p {
  margin: 0;
}

.summary__tables {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
  gap: var(--space-6);
  align-items: start;
}
</style>
