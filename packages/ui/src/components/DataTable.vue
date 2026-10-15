<script setup lang="ts" generic="Row extends object">
import type { TableColumn } from '../types'
import Skeleton from './Skeleton.vue'

/**
 * Tabla con el estilo de SAVI. Cada celda se reemplaza con el slot
 * `cell-<key>` (recibe `row`); el estado vacío con el slot `empty`. Con
 * `clickable`, la fila entera se activa con clic o con Enter.
 */
const props = withDefaults(
  defineProps<{
    columns: TableColumn[]
    rows: Row[]
    rowKey: keyof Row & string
    loading?: boolean
    clickable?: boolean
    emptyText?: string
    /** Texto para lectores de pantalla que describe la tabla. */
    caption?: string
  }>(),
  { emptyText: 'Sin resultados.' },
)

const emit = defineEmits<{ 'row-click': [row: Row] }>()

function cellValue(row: Row, key: string): unknown {
  return (row as Record<string, unknown>)[key]
}

function onRowKeydown(event: KeyboardEvent, row: Row): void {
  if (props.clickable && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault()
    emit('row-click', row)
  }
}
</script>

<template>
  <div class="ui-table__wrap">
    <table class="ui-table">
      <caption v-if="caption" class="ui-table__caption">{{ caption }}</caption>
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            scope="col"
            :style="{ width: column.width, textAlign: column.align ?? 'left' }"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody v-if="loading && rows.length === 0">
        <tr v-for="n in 3" :key="n">
          <td v-for="column in columns" :key="column.key"><Skeleton height="14px" width="70%" /></td>
        </tr>
      </tbody>
      <tbody v-else-if="rows.length === 0">
        <tr>
          <td :colspan="columns.length" class="ui-table__empty">
            <slot name="empty">{{ emptyText }}</slot>
          </td>
        </tr>
      </tbody>
      <tbody v-else>
        <tr
          v-for="row in rows"
          :key="String(row[rowKey])"
          :class="{ 'ui-table__row--clickable': clickable }"
          :tabindex="clickable ? 0 : undefined"
          @click="clickable && emit('row-click', row)"
          @keydown="onRowKeydown($event, row)"
        >
          <td
            v-for="column in columns"
            :key="column.key"
            :class="{ 'ui-table__mono': column.mono }"
            :style="{ textAlign: column.align ?? 'left' }"
          >
            <slot :name="`cell-${column.key}`" :row="row">{{ cellValue(row, column.key) ?? '—' }}</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.ui-table__wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
}

.ui-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: var(--text);
}

.ui-table__caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.ui-table th {
  padding: var(--space-3) var(--space-4);
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.ui-table td {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.ui-table tbody tr:last-child td {
  border-bottom: none;
}

.ui-table__row--clickable {
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
}

.ui-table__row--clickable:hover {
  background: var(--surface-subtle);
}

.ui-table__row--clickable:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: -2px;
}

.ui-table__mono {
  font-family: var(--font-mono);
  font-size: 12px;
}

.ui-table__empty {
  padding: var(--space-8) var(--space-4) !important;
  text-align: center !important;
  color: var(--text-muted);
}
</style>
