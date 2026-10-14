<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import BarChart from '@/components/BarChart.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import KpiCard from '@/components/KpiCard.vue'
import { consoleApi } from '@/lib/api'
import { formatDay, formatInt, formatUsd } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const { data, loading, error } = useAsync(() => consoleApi.overview())

const trend = computed(() =>
  (data.value?.trend ?? []).map((d) => ({ label: formatDay(d.day).slice(0, 5), value: d.turns })),
)
const alerts = computed(() => data.value?.open_alerts ?? { info: 0, warning: 0, critical: 0 })
</script>

<template>
  <div class="stack">
    <div class="spread">
      <h1>Resumen</h1>
      <FreshnessChip v-if="data" :seconds="data.freshness.seconds" />
    </div>
    <p v-if="loading && !data" class="muted">Cargando…</p>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>

    <template v-if="data">
      <p class="muted">Últimos 30 días.</p>
      <div class="grid-kpi">
        <KpiCard
          label="Clientes activos"
          :value="formatInt(data.clients.active)"
          :hint="`${data.clients.suspended} suspendidos`"
        />
        <KpiCard
          label="Instancias en línea"
          metric="online"
          :value="formatInt(data.instances.online)"
          :hint="`${data.instances.offline} sin conexión`"
        />
        <KpiCard
          label="Usuarios activos"
          metric="active_users"
          :value="formatInt(data.usage.active_users)"
        />
        <KpiCard label="Turnos" metric="turns" :value="formatInt(data.usage.turns)" />
        <KpiCard label="Costo" metric="cost_usd" :value="formatUsd(data.usage.cost_usd)" />
        <KpiCard
          label="Alertas abiertas"
          :value="formatInt(alerts.critical + alerts.warning + alerts.info)"
          :hint="`${alerts.critical} críticas · ${alerts.warning} avisos`"
        />
      </div>

      <section class="card">
        <h2>Turnos por día</h2>
        <BarChart :data="trend" :format="formatInt" />
      </section>

      <div class="two">
        <section class="stack">
          <h2>Proveedores y modelos</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Proveedor</th>
                  <th>Modelo</th>
                  <th class="num">Turnos</th>
                  <th class="num">Costo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in data.providers" :key="`${p.provider}-${p.model}`">
                  <td>{{ p.provider ?? '—' }}</td>
                  <td>{{ p.model ?? '—' }}</td>
                  <td class="num">{{ formatInt(p.turns) }}</td>
                  <td class="num">{{ formatUsd(p.cost_usd) }}</td>
                </tr>
                <tr v-if="!data.providers.length">
                  <td colspan="4" class="empty">Sin turnos en el período.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="stack">
          <h2>Versiones instaladas</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Versión</th>
                  <th class="num">Instancias</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="v in data.versions" :key="v.version ?? 'sin'">
                  <td>{{ v.version ?? 'Sin informar' }}</td>
                  <td class="num">{{ v.instances }}</td>
                </tr>
                <tr v-if="!data.versions.length">
                  <td colspan="2" class="empty">Todavía no hay instancias vinculadas.</td>
                </tr>
              </tbody>
            </table>
          </div>
          <RouterLink to="/instancias">Ver instancias</RouterLink>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.two {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.2rem;
}
</style>
