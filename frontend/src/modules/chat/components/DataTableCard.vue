<script setup lang="ts">
/**
 * Tabla de datos de una respuesta: vista previa y exportación completa.
 *
 * La vista previa está limitada a propósito (una tabla de cientos de filas no
 * se lee en un chat). Exportar baja TODAS las filas de la consulta, generadas
 * por el servidor desde la base, no desde el texto de la respuesta.
 */
import { computed, onMounted, ref, useTemplateRef } from 'vue'
import Popover from '@/components/ui/Popover.vue'
import { triggerDownload } from '@/lib/download'
import { HttpRequestError } from '@/lib/HttpClient'
import {
  type ExportFormat,
  type ResultSetPreview,
  resultSetService,
} from '../services/resultSetService'
import type { DataTableRef } from '../types'
import { formatPreviewCell, rowCountLabel } from '../utils/dataTables'

const props = defineProps<{ table: DataTableRef }>()

const COLLAPSED_ROWS = 8

const preview = ref<ResultSetPreview | null>(null)
const loadError = ref<string | null>(null)
const expanded = ref(false)
const exporting = ref<ExportFormat | null>(null)
const exportError = ref<string | null>(null)
const open = ref(false)
const trigger = useTemplateRef<HTMLButtonElement>('trigger')

const visibleRows = computed(() => {
  const rows = preview.value?.rows ?? []
  return expanded.value ? rows : rows.slice(0, COLLAPSED_ROWS)
})
const shownCount = computed(() => visibleRows.value.length)
const legend = computed(() =>
  rowCountLabel(shownCount.value, props.table.total_rows, props.table.total_is_lower_bound),
)
const canExpand = computed(() => (preview.value?.rows.length ?? 0) > COLLAPSED_ROWS)

onMounted(async () => {
  try {
    preview.value = await resultSetService.preview(props.table.id)
  } catch (error) {
    loadError.value =
      error instanceof HttpRequestError && error.status === 404
        ? 'Estos datos ya no están disponibles. Vuelva a hacer la consulta.'
        : 'No se pudieron cargar los datos.'
  }
})

const FORMATS: { format: ExportFormat; label: string }[] = [
  { format: 'xlsx', label: 'Excel (.xlsx)' },
  { format: 'pdf', label: 'PDF' },
  { format: 'csv', label: 'CSV' },
]

async function exportAs(format: ExportFormat): Promise<void> {
  open.value = false
  exporting.value = format
  exportError.value = null
  try {
    const blob = await resultSetService.export(props.table.id, format)
    const url = URL.createObjectURL(blob)
    triggerDownload(url, `${props.table.title.replace(/[\\/:*?"<>|]+/g, '-')}.${format}`)
    setTimeout(() => URL.revokeObjectURL(url), 0)
  } catch {
    exportError.value = 'No se pudo generar el archivo. Intente de nuevo.'
  } finally {
    exporting.value = null
  }
}
</script>

<template>
  <section class="data-card" data-testid="data-table-card">
    <header class="data-card__header">
      <div class="data-card__titles">
        <p class="data-card__title">{{ table.title }}</p>
        <p class="data-card__legend">{{ legend }}</p>
      </div>
      <button
        ref="trigger"
        type="button"
        class="data-card__export"
        :aria-expanded="open"
        :disabled="exporting !== null"
        @click="open = !open"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 3v12" />
          <path d="m7 11 5 5 5-5" />
          <path d="M5 21h14" />
        </svg>
        {{ exporting ? 'Generando…' : 'Exportar' }}
      </button>
      <Popover v-model:open="open" :anchor="trigger" side="bottom" align="end" :min-width="170">
        <button
          v-for="item in FORMATS"
          :key="item.format"
          type="button"
          class="menu__item"
          role="menuitem"
          @click="exportAs(item.format)"
        >
          {{ item.label }}
        </button>
      </Popover>
    </header>

    <p v-if="loadError" class="data-card__error">{{ loadError }}</p>
    <p v-else-if="!preview" class="data-card__muted">Cargando datos…</p>
    <div v-else class="data-card__scroll">
      <table>
        <thead>
          <tr>
            <th v-for="column in preview.columns" :key="column.key" :class="`is-${column.kind}`">
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, r) in visibleRows" :key="r">
            <td
              v-for="(column, c) in preview.columns"
              :key="column.key"
              :class="`is-${column.kind}`"
            >
              {{ formatPreviewCell(row[c], column.kind) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer v-if="preview" class="data-card__footer">
      <button v-if="canExpand" type="button" class="data-card__more" @click="expanded = !expanded">
        {{ expanded ? 'Ver menos' : 'Ver más filas' }}
      </button>
      <span v-if="table.total_rows > shownCount" class="data-card__hint">
        Para ver todas las filas, use Exportar.
      </span>
    </footer>
    <p v-if="exportError" class="data-card__error" role="alert">{{ exportError }}</p>
  </section>
</template>

<style scoped>
.data-card {
  margin: var(--space-3) 0 0;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  overflow: hidden;
}

.data-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--surface-subtle);
}

.data-card__title {
  margin: 0;
  font-size: 13px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.data-card__legend {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.data-card__export {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding: 5px var(--space-3);
  border: 1px solid var(--brand);
  border-radius: var(--r-sm);
  background: var(--brand);
  color: var(--text-on-brand, #fff);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.data-card__export:disabled {
  opacity: 0.7;
  cursor: progress;
}

.data-card__scroll {
  overflow-x: auto;
  max-height: 420px;
}

.data-card table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.data-card th,
.data-card td {
  padding: 6px var(--space-3);
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.data-card th {
  position: sticky;
  top: 0;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-subtle);
  background: var(--surface-elev);
}

.data-card .is-number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.data-card__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
}

.data-card__footer:empty {
  display: none;
}

.data-card__more {
  border: none;
  background: none;
  padding: 0;
  color: var(--brand);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.data-card__hint,
.data-card__muted {
  font-size: 12px;
  color: var(--text-muted);
}

.data-card__muted {
  margin: 0;
  padding: var(--space-3) var(--space-4);
}

.data-card__error {
  margin: 0;
  padding: var(--space-2) var(--space-4);
  font-size: 12.5px;
  color: var(--danger, #b42318);
}
</style>
