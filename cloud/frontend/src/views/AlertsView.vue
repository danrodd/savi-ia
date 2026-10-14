<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import type { Alert, Severity } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const status = ref('')
const severity = ref('')

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.alerts({
    status: status.value || undefined,
    severity: (severity.value || undefined) as Severity | undefined,
  }),
)
watch([status, severity], () => void reload())

const SEVERITY: Record<Severity, { label: string; tone: 'muted' | 'warn' | 'bad' }> = {
  info: { label: 'Info', tone: 'muted' },
  warning: { label: 'Aviso', tone: 'warn' },
  critical: { label: 'Crítica', tone: 'bad' },
}
const STATUS: Record<Alert['status'], string> = {
  open: 'Abierta',
  acknowledged: 'Reconocida',
  resolved: 'Resuelta',
}

const actionError = ref<string | null>(null)
const resolving = ref<string | null>(null)
const note = ref('')

async function acknowledge(alert: Alert): Promise<void> {
  actionError.value = null
  try {
    await consoleApi.acknowledgeAlert(alert.id)
    await reload()
  } catch (e) {
    actionError.value = errorMessage(e)
  }
}

async function resolve(alert: Alert): Promise<void> {
  actionError.value = null
  try {
    await consoleApi.resolveAlert(alert.id, note.value)
    resolving.value = null
    note.value = ''
    await reload()
  } catch (e) {
    actionError.value = errorMessage(e)
  }
}

function detail(alert: Alert): string {
  return Object.entries(alert.details)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(' · ')
}
</script>

<template>
  <div class="stack">
    <h1>Alertas</h1>
    <div class="row">
      <select v-model="status" class="select" aria-label="Estado">
        <option value="">Todas</option>
        <option value="open">Abiertas</option>
        <option value="acknowledged">Reconocidas</option>
        <option value="resolved">Resueltas</option>
      </select>
      <select v-model="severity" class="select" aria-label="Severidad">
        <option value="">Cualquier severidad</option>
        <option value="critical">Críticas</option>
        <option value="warning">Avisos</option>
        <option value="info">Info</option>
      </select>
    </div>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="actionError" class="error-text" role="alert">{{ actionError }}</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Severidad</th>
            <th>Regla</th>
            <th>Detalle</th>
            <th>Estado</th>
            <th>Abierta</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template v-for="a in data ?? []" :key="a.id">
            <tr>
              <td>
                <StatusBadge :tone="SEVERITY[a.severity].tone" :label="SEVERITY[a.severity].label" />
              </td>
              <td>
                <RouterLink :to="`/clientes/${a.client_id}`">{{ a.rule_code }}</RouterLink>
              </td>
              <td class="muted detail">{{ detail(a) }}</td>
              <td>
                {{ STATUS[a.status] }}
                <span v-if="a.acknowledged_by && a.status === 'acknowledged'" class="muted">
                  · {{ a.acknowledged_by }}
                </span>
              </td>
              <td>{{ relativeTime(a.opened_at) }}</td>
              <td>
                <div v-if="auth.can('alerts.manage') && a.status !== 'resolved'" class="row">
                  <button
                    v-if="a.status === 'open'"
                    class="btn btn-small"
                    type="button"
                    @click="acknowledge(a)"
                  >
                    Reconocer
                  </button>
                  <button class="btn btn-small" type="button" @click="resolving = a.id">
                    Resolver
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="resolving === a.id">
              <td colspan="6">
                <form class="row" @submit.prevent="resolve(a)">
                  <input v-model="note" placeholder="Nota (opcional)" maxlength="500" />
                  <button class="btn btn-primary btn-small" type="submit">Resolver alerta</button>
                  <button class="btn btn-small" type="button" @click="resolving = null">
                    Cancelar
                  </button>
                </form>
              </td>
            </tr>
          </template>
          <tr v-if="!loading && !(data?.length ?? 0)">
            <td colspan="6" class="empty">No hay alertas con esos filtros.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.select {
  width: auto;
}
.detail {
  max-width: 340px;
  word-break: break-word;
}
</style>
