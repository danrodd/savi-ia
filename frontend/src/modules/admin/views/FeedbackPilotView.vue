<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { formatFullDateTime } from '@/lib/dateTime'
import { triggerDownload } from '@/lib/download'
import { toast } from '@/lib/toast'
import FeedbackDetailDialog from '../components/FeedbackDetailDialog.vue'
import { useFeedbackStore } from '../stores/feedbackStore'
import type { FeedbackFilters, FeedbackItem } from '../types'
import {
  barPercent,
  emptyFeedbackFilters,
  FEEDBACK_RATING_LABELS,
  FEEDBACK_REASON_LABELS,
  feedbackExportRows,
  shortQuestion,
  topReasonLabel,
} from '../utils/feedback'

const store = useFeedbackStore()

const form = reactive<FeedbackFilters>({ ...store.filters })
const detail = ref<FeedbackItem | null>(null)
const detailOpen = ref(false)
const exporting = ref<'csv' | 'xlsx' | null>(null)

const summary = computed(() => store.summary)
const maxDaily = computed(() =>
  Math.max(0, ...(summary.value?.daily ?? []).map((d) => d.up + d.down)),
)
const models = computed(
  () =>
    [...new Set((summary.value?.by_model ?? []).map((m) => m.model).filter(Boolean))] as string[],
)

onMounted(() => void store.load())

function apply(): void {
  void store.applyFilters({ ...form })
}

function clear(): void {
  Object.assign(form, emptyFeedbackFilters())
  apply()
}

function openDetail(item: FeedbackItem): void {
  detail.value = item
  detailOpen.value = true
}

function who(item: FeedbackItem): string {
  return item.user_name || item.user_login || `#${item.user_id}`
}

function stamp(): string {
  return new Date().toISOString().slice(0, 10)
}

async function exportCsv(): Promise<void> {
  exporting.value = 'csv'
  try {
    const blob = await store.exportCsv()
    const url = URL.createObjectURL(blob)
    triggerDownload(url, `feedback-piloto-${stamp()}.csv`)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    toast.error((e as Error).message || 'No se pudo exportar el CSV.')
  } finally {
    exporting.value = null
  }
}

async function exportXlsx(): Promise<void> {
  exporting.value = 'xlsx'
  try {
    const items = await store.fetchAllItems()
    const XLSX = await import('xlsx')
    const ws = XLSX.utils.aoa_to_sheet(feedbackExportRows(items))
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Feedback')
    XLSX.writeFile(wb, `feedback-piloto-${stamp()}.xlsx`)
  } catch (e) {
    toast.error((e as Error).message || 'No se pudo exportar el Excel.')
  } finally {
    exporting.value = null
  }
}
</script>

<template>
  <section class="fp" data-testid="feedback-view">
    <header class="fp__header">
      <div>
        <h1 class="fp__title">Feedback del piloto</h1>
        <p class="fp__subtitle">
          Lo que las personas opinan de cada respuesta de SAVI, con la pregunta y la respuesta a
          la vista.
        </p>
      </div>
      <div class="fp__exports">
        <button type="button" class="fp__btn" :disabled="exporting !== null" @click="exportCsv">
          Exportar CSV
        </button>
        <button type="button" class="fp__btn" :disabled="exporting !== null" @click="exportXlsx">
          Exportar Excel (.xlsx)
        </button>
      </div>
    </header>

    <div class="fp__cards">
      <article class="fp__card">
        <span class="fp__card-label">Respuestas calificadas</span>
        <strong class="fp__card-value">{{ summary?.total ?? 0 }}</strong>
      </article>
      <article class="fp__card">
        <span class="fp__card-label">% positivas</span>
        <strong class="fp__card-value">
          {{ summary?.positive_pct == null ? '—' : `${summary.positive_pct}%` }}
        </strong>
      </article>
      <article class="fp__card">
        <span class="fp__card-label">Con 👎</span>
        <strong class="fp__card-value">{{ summary?.down ?? 0 }}</strong>
      </article>
      <article class="fp__card">
        <span class="fp__card-label">Motivo principal</span>
        <strong class="fp__card-text">{{ topReasonLabel(summary?.top_reasons ?? []) }}</strong>
      </article>
    </div>

    <section v-if="summary && summary.daily.length" class="fp__chart" aria-label="Calificaciones por día">
      <h2 class="fp__h2">Por día</h2>
      <ol class="fp__bars">
        <li v-for="d in summary.daily" :key="d.day" class="fp__bar">
          <div class="fp__bar-stack" :title="`${d.day}: ${d.up} 👍 · ${d.down} 👎`">
            <span class="fp__bar-down" :style="{ height: `${barPercent(d.down, maxDaily)}%` }" />
            <span class="fp__bar-up" :style="{ height: `${barPercent(d.up, maxDaily)}%` }" />
          </div>
          <span class="fp__bar-day">{{ d.day.slice(5) }}</span>
        </li>
      </ol>
    </section>

    <form class="fp__filters" @submit.prevent="apply">
      <label>
        <span>Calificación</span>
        <select v-model="form.rating">
          <option value="">Todas</option>
          <option value="up">{{ FEEDBACK_RATING_LABELS.up }}</option>
          <option value="down">{{ FEEDBACK_RATING_LABELS.down }}</option>
        </select>
      </label>
      <label>
        <span>Motivo</span>
        <select v-model="form.reason" :disabled="form.rating === 'up'">
          <option value="">Todos</option>
          <option v-for="(label, key) in FEEDBACK_REASON_LABELS" :key="key" :value="key">
            {{ label }}
          </option>
        </select>
      </label>
      <label>
        <span>Desde</span>
        <input v-model="form.from" type="date" />
      </label>
      <label>
        <span>Hasta</span>
        <input v-model="form.to" type="date" />
      </label>
      <label>
        <span>Modelo</span>
        <input v-model="form.model" type="text" list="fp-models" placeholder="Cualquiera" />
        <datalist id="fp-models">
          <option v-for="m in models" :key="m" :value="m" />
        </datalist>
      </label>
      <label>
        <span>Usuario</span>
        <input v-model="form.user" type="text" placeholder="Código de usuario" />
      </label>
      <label class="fp__filters-text">
        <span>Buscar en comentarios</span>
        <input v-model="form.text" type="search" placeholder="Palabra o frase" />
      </label>
      <div class="fp__filters-actions">
        <button type="submit" class="fp__btn fp__btn--primary">Filtrar</button>
        <button type="button" class="fp__btn" @click="clear">Limpiar</button>
      </div>
    </form>

    <p v-if="store.error" class="fp__error" role="alert">{{ store.error }}</p>

    <div class="fp__table-wrap">
      <table class="fp__table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Usuario</th>
            <th>Calificación</th>
            <th>Motivo</th>
            <th>Pregunta</th>
            <th>Modelo</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!store.loading && store.items.length === 0">
            <td colspan="6" class="fp__empty">Todavía no hay calificaciones con estos filtros.</td>
          </tr>
          <tr
            v-for="item in store.items"
            :key="item.id"
            class="fp__row"
            tabindex="0"
            @click="openDetail(item)"
            @keydown.enter="openDetail(item)"
          >
            <td>{{ formatFullDateTime(item.created_at) }}</td>
            <td>{{ who(item) }}</td>
            <td>
              <span class="fp__rating" :class="`fp__rating--${item.rating}`">
                {{ item.rating === 'up' ? '👍' : '👎' }}
                {{ FEEDBACK_RATING_LABELS[item.rating] }}
              </span>
            </td>
            <td>{{ item.reason ? FEEDBACK_REASON_LABELS[item.reason] : '—' }}</td>
            <td class="fp__question">{{ shortQuestion(item.question) }}</td>
            <td>{{ item.model ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav v-if="store.pageCount > 1" class="fp__pager" aria-label="Páginas">
      <button type="button" class="fp__btn" :disabled="store.page === 0" @click="store.goToPage(store.page - 1)">
        Anterior
      </button>
      <span>Página {{ store.page + 1 }} de {{ store.pageCount }}</span>
      <button
        type="button"
        class="fp__btn"
        :disabled="store.page >= store.pageCount - 1"
        @click="store.goToPage(store.page + 1)"
      >
        Siguiente
      </button>
    </nav>

    <FeedbackDetailDialog v-model:open="detailOpen" :item="detail" />
  </section>
</template>

<style scoped>
.fp {
  display: grid;
  gap: var(--space-5);
}

.fp__header {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  justify-content: space-between;
  align-items: flex-start;
}

.fp__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
}

.fp__subtitle {
  margin: 0;
  max-width: 56ch;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted);
}

.fp__exports {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.fp__btn {
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font-family: inherit;
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.fp__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.fp__btn--primary {
  background: var(--brand-solid);
  border-color: var(--brand);
  color: var(--text-on-brand);
}

.fp__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: var(--space-3);
}

.fp__card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
}

.fp__card-label {
  font-size: 11.5px;
  color: var(--text-subtle);
}

.fp__card-value {
  font-family: var(--font-display, var(--font-sans));
  font-size: 28px;
}

.fp__card-text {
  font-size: 14px;
  line-height: 1.35;
}

.fp__h2 {
  margin: 0 0 var(--space-3);
  font-size: 13px;
  color: var(--text-muted);
}

.fp__bars {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
  height: 120px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
}

.fp__bar {
  display: grid;
  gap: 4px;
  min-width: 26px;
  height: 100%;
  grid-template-rows: 1fr auto;
  justify-items: center;
}

.fp__bar-stack {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  width: 18px;
  height: 100%;
}

.fp__bar-up {
  background: var(--text-muted);
  border-radius: 3px 3px 0 0;
}

.fp__bar-down {
  background: var(--brand);
}

.fp__bar-day {
  font-size: 10px;
  color: var(--text-subtle);
  font-family: var(--font-mono);
}

.fp__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-3);
  align-items: end;
}

.fp__filters label {
  display: grid;
  min-width: 0;
  gap: 4px;
  font-size: 11.5px;
  color: var(--text-muted);
}

.fp__filters input,
.fp__filters select {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.fp__filters-text {
  grid-column: span 2;
}

.fp__filters-actions {
  display: flex;
  gap: var(--space-2);
}

.fp__error {
  margin: 0;
  color: var(--brand);
  font-size: 13px;
}

.fp__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.fp__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.fp__table th,
.fp__table td {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.fp__table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-subtle);
}

.fp__row {
  cursor: pointer;
}

.fp__row:hover,
.fp__row:focus-visible {
  background: var(--surface-subtle);
  outline: none;
}

.fp__question {
  max-width: 340px;
}

.fp__rating--down {
  color: var(--brand-strong);
}

.fp__empty {
  text-align: center;
  color: var(--text-muted);
}

.fp__pager {
  display: flex;
  gap: var(--space-4);
  align-items: center;
  justify-content: center;
  font-size: 12.5px;
}
</style>
