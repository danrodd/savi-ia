<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import { formatFullDateTime } from '@/lib/dateTime'
import { HttpRequestError } from '@/lib/HttpClient'
import { updatesService } from '../services/updatesService'
import type { UpdateHistory, UpdateStatus } from '../types'
import { canApplyNow, channelLabel, notifyStatusChanged, outcomeLabel } from '../utils/adminView'

const status = ref<UpdateStatus | null>(null)
const history = ref<UpdateHistory | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const checking = ref(false)
const applying = ref(false)
const actionError = ref<string | null>(null)

const showApply = computed(() => status.value !== null && canApplyNow(status.value))
const records = computed(() => history.value?.records ?? [])

function describe(error: unknown, fallback: string): string {
  return error instanceof HttpRequestError ? error.message : fallback
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    ;[status.value, history.value] = await Promise.all([
      updatesService.getStatus(),
      updatesService.getHistory(),
    ])
  } catch (error) {
    loadError.value = describe(error, 'No se pudo leer el estado de las actualizaciones.')
  } finally {
    loading.value = false
  }
}

async function checkNow(): Promise<void> {
  checking.value = true
  actionError.value = null
  try {
    status.value = await updatesService.check()
    notifyStatusChanged()
  } catch (error) {
    actionError.value = describe(error, 'No se pudo buscar actualizaciones. Intente de nuevo.')
  } finally {
    checking.value = false
  }
}

async function applyNow(): Promise<void> {
  applying.value = true
  actionError.value = null
  try {
    status.value = await updatesService.apply()
    // El aviso global es quien muestra el avance y espera el reinicio.
    notifyStatusChanged()
  } catch (error) {
    actionError.value = describe(error, 'No se pudo iniciar la actualización. Intente de nuevo.')
  } finally {
    applying.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section data-testid="updates-admin">
    <header class="aupd__header">
      <h1 class="aupd__title">Actualizaciones</h1>
      <p class="aupd__subtitle">
        Versión instalada, servidor de actualizaciones e historial de los intentos de instalación.
      </p>
    </header>

    <p v-if="loading" class="aupd__muted">Cargando…</p>
    <p v-else-if="loadError" class="aupd__error" role="alert">{{ loadError }}</p>

    <template v-else-if="status && history">
      <p v-if="!status.enabled" class="aupd__muted" data-testid="updates-disabled">
        Las actualizaciones no están activas en esta instalación: es una versión de desarrollo o
        no hay un servidor de actualizaciones configurado.
      </p>

      <dl class="aupd__facts">
        <div>
          <dt>Versión instalada</dt>
          <dd data-testid="current-version">{{ status.current_version ?? '—' }}</dd>
        </div>
        <div>
          <dt>Canal</dt>
          <dd>{{ channelLabel(history.channel) }}</dd>
        </div>
        <div>
          <dt>Servidor</dt>
          <dd class="aupd__break">{{ history.server || '—' }}</dd>
        </div>
        <div>
          <dt>Última comprobación</dt>
          <dd>{{ status.checked_at ? formatFullDateTime(status.checked_at) : 'Todavía no' }}</dd>
        </div>
        <div>
          <dt>Versión disponible</dt>
          <dd data-testid="available-version">{{ status.available_version ?? 'Ninguna' }}</dd>
        </div>
      </dl>

      <p v-if="status.notes" class="aupd__notes" data-testid="update-notes">{{ status.notes }}</p>
      <p v-if="status.error" class="aupd__error" role="alert">{{ status.error }}</p>

      <div v-if="status.enabled" class="aupd__actions">
        <Button variant="secondary" :loading="checking" @click="checkNow">Buscar ahora</Button>
        <Button v-if="showApply" :loading="applying" @click="applyNow">Actualizar ahora</Button>
      </div>
      <p v-if="actionError" class="aupd__error" role="alert">{{ actionError }}</p>

      <h2 class="aupd__section">Historial</h2>
      <p v-if="records.length === 0" class="aupd__muted" data-testid="history-empty">
        Todavía no hay intentos de instalación.
      </p>
      <div v-else class="aupd__table-wrap">
        <table class="aupd__table" data-testid="history-table">
          <thead>
            <tr>
              <th scope="col">Fecha</th>
              <th scope="col">De</th>
              <th scope="col">A</th>
              <th scope="col">Resultado</th>
              <th scope="col">Detalle</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in records" :key="record.attempt_id">
              <td>{{ formatFullDateTime(record.finished_at) }}</td>
              <td>{{ record.from_version }}</td>
              <td>{{ record.to_version }}</td>
              <td>
                <span class="aupd__outcome" :class="`aupd__outcome--${record.outcome}`">
                  {{ outcomeLabel(record.outcome) }}
                </span>
              </td>
              <td>{{ record.message }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.aupd__header {
  margin-bottom: var(--space-6);
}

.aupd__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.aupd__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 56ch;
  line-height: 1.5;
}

.aupd__muted {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  color: var(--text-muted);
}

.aupd__error {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--danger, #b42318);
}

.aupd__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: var(--space-4);
  margin: 0 0 var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
}

.aupd__facts dt {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
}

.aupd__facts dd {
  margin: var(--space-1) 0 0;
  font-size: 14px;
  font-weight: var(--fw-medium);
  color: var(--text);
}

.aupd__break {
  overflow-wrap: anywhere;
}

.aupd__notes {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  color: var(--text);
  white-space: pre-line;
}

.aupd__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.aupd__section {
  margin: 0 0 var(--space-3);
  font-size: 16px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.aupd__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.aupd__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.aupd__table th,
.aupd__table td {
  padding: var(--space-3);
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}

.aupd__table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
  background: var(--surface-subtle);
}

.aupd__table tbody tr:last-child td {
  border-bottom: none;
}

.aupd__outcome {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--r-sm);
  font-size: 12px;
  font-weight: var(--fw-medium);
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.aupd__outcome--installed {
  background: var(--brand-soft);
  color: var(--brand-strong);
}
</style>
