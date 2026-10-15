<script setup lang="ts">
import { Alert, Button, Card, DataTable, PageHeader, Skeleton, type TableColumn } from '@savi/ui'
import { Activity, Bell, Building2, DollarSign, Server, Users } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import BarChart from '@/components/BarChart.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import KpiCard from '@/components/KpiCard.vue'
import { consoleApi } from '@/lib/api'
import { formatDay, formatInt, formatUsd } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const router = useRouter()
const { data, loading, error, reload } = useAsync(() => consoleApi.overview())

const trend = computed(() =>
  (data.value?.trend ?? []).map((d) => ({ label: formatDay(d.day).slice(0, 5), value: d.turns })),
)
const alerts = computed(() => data.value?.open_alerts ?? { info: 0, warning: 0, critical: 0 })
const openAlerts = computed(() => alerts.value.critical + alerts.value.warning + alerts.value.info)

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
</script>

<template>
  <div>
    <PageHeader title="Resumen" description="Cómo vienen los clientes y sus instalaciones en los últimos 30 días.">
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

      <div v-if="loading && !data" class="grid-kpi">
        <Card v-for="n in 6" :key="n" padding="md">
          <Skeleton height="12px" width="50%" />
          <Skeleton height="26px" width="40%" style="margin-top: 12px" />
        </Card>
      </div>

      <template v-if="data">
        <Alert v-if="alerts.critical > 0" tone="danger" title="Hay alertas críticas abiertas">
          {{ alerts.critical }} {{ alerts.critical === 1 ? 'alerta crítica necesita' : 'alertas críticas necesitan' }}
          atención.
          <template #action>
            <Button size="sm" @click="router.push('/alertas')">Ver alertas</Button>
          </template>
        </Alert>

        <div class="grid-kpi">
          <KpiCard
            label="Clientes activos"
            :icon="Building2"
            :value="formatInt(data.clients.active)"
            :hint="`${data.clients.suspended} suspendidos`"
          />
          <KpiCard
            label="Instancias en línea"
            metric="online"
            :icon="Server"
            :tone="data.instances.offline > 0 ? 'warning' : 'success'"
            :value="formatInt(data.instances.online)"
            :hint="`${data.instances.offline} sin conexión`"
          />
          <KpiCard
            label="Usuarios activos"
            metric="active_users"
            :icon="Users"
            :value="formatInt(data.usage.active_users)"
          />
          <KpiCard label="Turnos" metric="turns" :icon="Activity" :value="formatInt(data.usage.turns)" />
          <KpiCard label="Costo" metric="cost_usd" :icon="DollarSign" :value="formatUsd(data.usage.cost_usd)" />
          <KpiCard
            label="Alertas abiertas"
            :icon="Bell"
            :tone="alerts.critical > 0 ? 'danger' : alerts.warning > 0 ? 'warning' : 'neutral'"
            :value="formatInt(openAlerts)"
            :hint="`${alerts.critical} críticas · ${alerts.warning} avisos`"
          />
        </div>

        <Card title="Turnos por día">
          <BarChart :data="trend" :format="formatInt" />
        </Card>

        <div class="two">
          <Card title="Proveedores y modelos" padding="none">
            <DataTable :columns="PROVIDER_COLUMNS" :rows="providers" row-key="key" empty-text="Sin turnos en el período.">
              <template #cell-provider="{ row }">{{ row.provider ?? '—' }}</template>
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
</style>
