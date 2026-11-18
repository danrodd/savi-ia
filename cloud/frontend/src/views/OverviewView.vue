<script setup lang="ts">
import { Alert, Button, Card, DataTable, PageHeader, Skeleton, type TableColumn } from '@savi/ui'
import { Activity, DollarSign, Server, Users } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AttentionPanel from '@/components/AttentionPanel.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import KpiCard from '@/components/KpiCard.vue'
import StackedBarChart, { type StackDay, type StackSeries } from '@/components/StackedBarChart.vue'
import { consoleApi } from '@/lib/api'
import { clientPath } from '@/lib/clientRoutes'
import { formatDay, formatInt, formatUsd, providerLabel, variation } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const router = useRouter()
const { data, loading, error, reload } = useAsync(() => consoleApi.overview())

const OTHERS = 'otros'
const SERIES_COLORS = ['--chart-s1', '--chart-s2', '--chart-s3']

const previous = computed(() => data.value?.previous_usage)
const changes = computed(() => {
  const now = data.value?.usage
  const before = previous.value
  if (!now) return { turns: null, cost: null, users: null }
  return {
    turns: variation(now.turns, before?.turns),
    cost: variation(Number(now.cost_usd), before ? Number(before.cost_usd) : null),
    users: variation(now.active_users, before?.active_users),
  }
})

// El color sigue al cliente según su lugar en el ranking; el resto se suma en "Otros".
const series = computed<StackSeries[]>(() => {
  const rows = data.value?.trend_by_client ?? []
  const shown = new Set(rows.map((r) => r.client_id))
  const named = (data.value?.top_clients ?? [])
    .filter((c) => shown.has(c.client_id))
    .slice(0, SERIES_COLORS.length)
    .map((c, index) => ({
      key: c.client_id,
      label: c.name || c.code,
      color: SERIES_COLORS[index] ?? '--chart-1',
    }))
  return shown.has(null)
    ? [...named, { key: OTHERS, label: 'Otros', color: '--chart-other' }]
    : named
})

const days = computed<StackDay[]>(() => {
  const byDay = new Map<string, Record<string, number>>()
  for (const row of data.value?.trend_by_client ?? []) {
    const values = byDay.get(row.day) ?? {}
    values[row.client_id ?? OTHERS] = (values[row.client_id ?? OTHERS] ?? 0) + row.turns
    byDay.set(row.day, values)
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, values]) => ({ label: formatDay(day).slice(0, 5), values }))
})

const TOP_COLUMNS: TableColumn[] = [
  { key: 'name', label: 'Cliente', card: 'title' },
  { key: 'turns', label: 'Turnos', align: 'right' },
  { key: 'active_users', label: 'Personas', align: 'right' },
  { key: 'cost_usd', label: 'Costo', align: 'right' },
]
const PROVIDER_COLUMNS: TableColumn[] = [
  { key: 'provider', label: 'Proveedor' },
  { key: 'model', label: 'Modelo' },
  { key: 'turns', label: 'Turnos', align: 'right' },
  { key: 'cost_usd', label: 'Costo', align: 'right' },
]
const VERSION_COLUMNS: TableColumn[] = [
  { key: 'version', label: 'Versión', mono: true },
  { key: 'instances', label: 'Instancias', align: 'right' },
]

const providers = computed(() =>
  (data.value?.providers ?? []).map((p) => ({ ...p, key: `${p.provider}-${p.model}` })),
)
const versions = computed(() =>
  (data.value?.versions ?? []).map((v) => ({ ...v, key: v.version ?? 'sin-informar' })),
)
const alerts = computed(() => data.value?.open_alerts ?? { info: 0, warning: 0, critical: 0 })
</script>

<template>
  <div>
    <PageHeader title="Resumen" description="Qué atender hoy y cómo vienen los clientes en los últimos 30 días.">
      <template #actions>
        <FreshnessChip v-if="data" :seconds="data.freshness.seconds" />
      </template>
    </PageHeader>

    <div class="stack">
      <Alert v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </Alert>

      <AttentionPanel v-if="auth.can('alerts.read')" />
      <!-- Sin acceso a las alertas, al menos se avisa que hay críticas. -->
      <Alert v-else-if="alerts.critical > 0" tone="danger" title="Hay alertas críticas abiertas">
        {{ alerts.critical }} {{ alerts.critical === 1 ? 'alerta crítica necesita' : 'alertas críticas necesitan' }}
        atención.
        <template #action>
          <Button size="sm" @click="router.push('/alertas')">Ver alertas</Button>
        </template>
      </Alert>

      <div v-if="loading && !data" class="grid-kpi">
        <Card v-for="n in 4" :key="n" padding="md">
          <Skeleton height="12px" width="50%" />
          <Skeleton height="26px" width="40%" style="margin-top: 12px" />
        </Card>
      </div>

      <template v-if="data">
        <div class="kpis">
          <KpiCard
            label="Turnos"
            metric="turns"
            :icon="Activity"
            :value="formatInt(data.usage.turns)"
            :change="changes.turns"
            hint="Sin datos del periodo anterior"
          />
          <KpiCard
            label="Costo"
            metric="cost_usd"
            :icon="DollarSign"
            :value="formatUsd(data.usage.cost_usd)"
            :change="changes.cost"
            hint="Sin datos del periodo anterior"
          />
          <KpiCard
            label="Personas activas"
            metric="active_users"
            :icon="Users"
            :value="formatInt(data.usage.active_users)"
            :change="changes.users"
            hint="Sin datos del periodo anterior"
          />
          <KpiCard
            label="Instalaciones en línea"
            metric="online"
            :icon="Server"
            :tone="data.instances.offline > 0 ? 'warning' : 'neutral'"
            :value="formatInt(data.instances.online)"
            :hint="`${data.instances.offline} sin conexión · ${data.clients.active} clientes activos`"
          />
        </div>

        <div class="usage">
          <Card title="Turnos por día y por cliente">
            <StackedBarChart :series="series" :days="days" :format="formatInt" />
          </Card>

          <Card title="Clientes con más uso" padding="none">
            <DataTable
              :columns="TOP_COLUMNS"
              :rows="data.top_clients ?? []"
              row-key="client_id"
              caption="Clientes con más uso"
              empty-text="Sin turnos en el período."
            >
              <template #cell-name="{ row }">
                <RouterLink :to="clientPath(row.client_id, 'resumen')">{{ row.name || row.code }}</RouterLink>
              </template>
              <template #cell-turns="{ row }"><span class="num">{{ formatInt(row.turns) }}</span></template>
              <template #cell-active_users="{ row }">
                <span class="num">{{ formatInt(row.active_users) }}</span>
              </template>
              <template #cell-cost_usd="{ row }"><span class="num">{{ formatUsd(row.cost_usd) }}</span></template>
            </DataTable>
          </Card>
        </div>

        <div class="two">
          <Card title="Proveedores y modelos" padding="none">
            <DataTable :columns="PROVIDER_COLUMNS" :rows="providers" row-key="key" empty-text="Sin turnos en el período.">
              <template #cell-provider="{ row }">{{ providerLabel(row.provider) }}</template>
              <template #cell-model="{ row }">{{ row.model ?? '—' }}</template>
              <template #cell-turns="{ row }"><span class="num">{{ formatInt(row.turns) }}</span></template>
              <template #cell-cost_usd="{ row }"><span class="num">{{ formatUsd(row.cost_usd) }}</span></template>
            </DataTable>
          </Card>

          <Card title="Versiones instaladas" padding="none">
            <template #actions>
              <RouterLink to="/instancias" class="link">Ver instancias</RouterLink>
            </template>
            <DataTable
              :columns="VERSION_COLUMNS"
              :rows="versions"
              row-key="key"
              empty-text="Todavía no hay instancias vinculadas."
            >
              <template #cell-version="{ row }">
                <RouterLink
                  v-if="row.version"
                  :to="{ path: '/instancias', query: { version: row.version } }"
                  data-test="version-link"
                >
                  {{ row.version }}
                </RouterLink>
                <template v-else>Sin informar</template>
              </template>
            </DataTable>
          </Card>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* Cuatro cifras en una fila: sin huecos en la grilla. */
.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
}

.usage {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: var(--space-6);
  align-items: start;
}

.two {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
  gap: var(--space-6);
  align-items: start;
}

.link {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}

@media (max-width: 1100px) {
  .kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .usage {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 560px) {
  .kpis {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
