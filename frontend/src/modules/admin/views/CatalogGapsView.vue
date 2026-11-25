<script setup lang="ts">
/**
 * Vacíos del catálogo: preguntas que SAVI no pudo responder con su catálogo de
 * datos (las resolvió con consulta libre, la consulta falló o se quedó sin
 * consultas). Es lo que se revisa cada mes para sumar al catálogo.
 *
 * Las preguntas no salen de esta instalación.
 */
import { Button } from '@savi/ui'
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { formatFullDateTime } from '@/lib/dateTime'
import { triggerDownload } from '@/lib/download'
import { HttpRequestError } from '@/lib/HttpClient'
import { toast } from '@/lib/toast'
import {
  type CatalogGapReport,
  catalogGapsService,
  GAP_KIND_LABELS,
  type GapKind,
} from '../services/catalogGapsService'

const KINDS: GapKind[] = ['free_query', 'failed_query', 'query_limit']

const report = ref<CatalogGapReport | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const exporting = ref(false)
const form = reactive({ from: '', to: '' })

const period = computed(() => ({ from: form.from || undefined, to: form.to || undefined }))

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    report.value = await catalogGapsService.report(period.value)
  } catch (error) {
    loadError.value =
      error instanceof HttpRequestError ? error.message : 'No se pudo leer el reporte de vacíos.'
  } finally {
    loading.value = false
  }
}

async function exportCsv(): Promise<void> {
  exporting.value = true
  try {
    const blob = await catalogGapsService.exportCsv(period.value)
    const url = URL.createObjectURL(blob)
    triggerDownload(url, `vacios-catalogo-${new Date().toISOString().slice(0, 10)}.csv`)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    toast.error((e as Error).message || 'No se pudo exportar el CSV.')
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <header class="gaps__header">
      <h1 class="gaps__title">Vacíos del catálogo</h1>
      <p class="gaps__subtitle">
        Preguntas que SAVI no pudo responder con su catálogo de datos. Las más frecuentes son las
        que conviene sumar. Las preguntas no salen de esta instalación.
      </p>
    </header>

    <form class="gaps__filters" @submit.prevent="load">
      <label class="gaps__field">
        <span>Desde</span>
        <input v-model="form.from" type="date" data-testid="gaps-from" />
      </label>
      <label class="gaps__field">
        <span>Hasta</span>
        <input v-model="form.to" type="date" data-testid="gaps-to" />
      </label>
      <Button type="submit" variant="secondary">Consultar</Button>
      <Button
        type="button"
        variant="secondary"
        :disabled="exporting || !report || report.gaps.length === 0"
        @click="exportCsv"
      >
        Exportar CSV
      </Button>
    </form>
    <p class="gaps__muted">Sin fechas, se muestran los últimos 30 días.</p>

    <p v-if="loading" class="gaps__muted">Cargando…</p>
    <p v-else-if="loadError" class="gaps__error" role="alert">{{ loadError }}</p>
    <template v-else-if="report">
      <ul class="gaps__totals" data-testid="gaps-totals">
        <li v-for="kind in KINDS" :key="kind" class="gaps__total">
          <strong>{{ report.totals[kind] ?? 0 }}</strong>
          <span>{{ GAP_KIND_LABELS[kind] }}</span>
        </li>
      </ul>

      <p v-if="report.gaps.length === 0" class="gaps__muted" data-testid="gaps-empty">
        No hubo vacíos en este periodo: el catálogo respondió todas las preguntas.
      </p>
      <template v-else>
        <section v-if="report.top_tables.length" class="gaps__block">
          <h2 class="gaps__h2">Tablas del ERP más consultadas sin catálogo</h2>
          <ol class="gaps__tables" data-testid="gaps-top-tables">
            <li v-for="t in report.top_tables" :key="t.table">
              <code>{{ t.table }}</code>
              <span class="gaps__muted-inline">{{ t.times }} {{ t.times === 1 ? 'vez' : 'veces' }}</span>
            </li>
          </ol>
        </section>

        <div class="gaps__table-wrap">
          <table class="gaps__table" data-testid="gaps-table">
            <thead>
              <tr>
                <th scope="col">Pregunta</th>
                <th scope="col">Qué pasó</th>
                <th scope="col">Veces</th>
                <th scope="col">Última vez</th>
                <th scope="col">Tablas del ERP</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="gap in report.gaps" :key="`${gap.conversation_id}-${gap.question}`">
                <td class="gaps__question">{{ gap.question }}</td>
                <td>
                  <span v-for="kind in gap.kinds" :key="kind" class="gaps__kind">
                    {{ GAP_KIND_LABELS[kind] }}
                  </span>
                </td>
                <td>{{ gap.times }}</td>
                <td>{{ formatFullDateTime(gap.last_at) }}</td>
                <td>
                  <code v-for="t in gap.tables" :key="t" class="gaps__code">{{ t }}</code>
                  <span v-if="gap.tables.length === 0">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <p class="gaps__muted gaps__footer">
        Las respuestas que no se pudieron completar están en
        <RouterLink :to="{ name: 'admin-failed-turns' }">Turnos fallidos</RouterLink>.
      </p>
    </template>
  </section>
</template>

<style scoped>
.gaps__header {
  margin-bottom: var(--space-6);
}

.gaps__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.gaps__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 64ch;
  line-height: 1.5;
}

.gaps__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.gaps__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: 12px;
  color: var(--text-muted);
}

.gaps__field input {
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.gaps__muted {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  color: var(--text-muted);
}

.gaps__muted-inline {
  margin-left: var(--space-2);
  font-size: 12px;
  color: var(--text-muted);
}

.gaps__error {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--danger, #b42318);
}

.gaps__totals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-3);
  margin: 0 0 var(--space-6);
  padding: 0;
  list-style: none;
}

.gaps__total {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--text-muted);
}

.gaps__total strong {
  font-size: 22px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.gaps__block {
  margin-bottom: var(--space-6);
}

.gaps__h2 {
  margin: 0 0 var(--space-3);
  font-size: 14px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.gaps__tables {
  margin: 0;
  padding-left: var(--space-5, 20px);
  font-size: 13px;
  line-height: 1.8;
}

.gaps__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.gaps__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.gaps__table th,
.gaps__table td {
  padding: var(--space-3);
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}

.gaps__table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
  background: var(--surface-subtle);
}

.gaps__table tbody tr:last-child td {
  border-bottom: none;
}

.gaps__question {
  max-width: 48ch;
  color: var(--text);
}

.gaps__kind {
  display: inline-block;
  margin: 0 var(--space-1) var(--space-1) 0;
  padding: 2px var(--space-2);
  border-radius: var(--r-sm);
  font-size: 12px;
  font-weight: var(--fw-medium);
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.gaps__code {
  display: block;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  color: var(--text);
}

.gaps__footer {
  margin-top: var(--space-4);
}
</style>
