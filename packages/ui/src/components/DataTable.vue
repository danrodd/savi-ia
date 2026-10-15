<script setup lang="ts" generic="Row extends object">
import { useMediaQuery } from '@vueuse/core'
import { computed } from 'vue'
import type { TableColumn } from '../types'
import Skeleton from './Skeleton.vue'

/**
 * Tabla con el estilo de SAVI. Cada celda se reemplaza con el slot
 * `cell-<key>` (recibe `row`); el estado vacío con el slot `empty`. Con
 * `clickable`, la fila entera se activa con clic o con Enter.
 *
 * Con `cardsBelow` (px), en pantallas más angostas cada fila se muestra como tarjeta: así no
 * se corta horizontalmente. Las columnas se reparten según `TableColumn.card`. Sin la prop, la
 * tabla se ve igual que siempre.
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
    /** Ancho (px) por debajo del cual las filas pasan a tarjetas. */
    cardsBelow?: number
  }>(),
  { emptyText: 'Sin resultados.' },
)

const narrow = useMediaQuery(() =>
  props.cardsBelow ? `(max-width: ${props.cardsBelow - 1}px)` : 'not all',
)
const asCards = computed(() => Boolean(props.cardsBelow) && narrow.value)

function placement(column: TableColumn): 'title' | 'footer' | 'hidden' | 'field' {
  if (column.card) return column.card
  return column.label === '' ? 'footer' : 'field'
}

const titleColumns = computed(() => props.columns.filter((c) => placement(c) === 'title'))
const fieldColumns = computed(() => props.columns.filter((c) => placement(c) === 'field'))
const footerColumns = computed(() => props.columns.filter((c) => placement(c) === 'footer'))

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
  <div v-if="asCards" class="ui-cards" data-test="table-cards">
    <p v-if="caption" class="ui-table__caption">{{ caption }}</p>
    <ul v-if="loading && rows.length === 0" class="ui-cards__list">
      <li v-for="n in 3" :key="n" class="ui-cards__item"><Skeleton height="14px" width="70%" /></li>
    </ul>
    <div v-else-if="rows.length === 0" class="ui-table__empty ui-cards__empty">
      <slot name="empty">{{ emptyText }}</slot>
    </div>
    <ul v-else class="ui-cards__list">
      <li
        v-for="row in rows"
        :key="String(row[rowKey])"
        class="ui-cards__item"
        :class="{ 'ui-cards__item--clickable': clickable }"
        :tabindex="clickable ? 0 : undefined"
        data-test="table-card"
        @click="clickable && emit('row-click', row)"
        @keydown="onRowKeydown($event, row)"
      >
        <div v-if="titleColumns.length" class="ui-cards__title">
          <div v-for="column in titleColumns" :key="column.key" class="ui-cards__title-item">
            <slot :name="`cell-${column.key}`" :row="row">{{ cellValue(row, column.key) ?? '—' }}</slot>
          </div>
        </div>
        <dl v-if="fieldColumns.length" class="ui-cards__fields">
          <div v-for="column in fieldColumns" :key="column.key" class="ui-cards__field">
            <dt>{{ column.label }}</dt>
            <dd :class="{ 'ui-table__mono': column.mono }">
              <slot :name="`cell-${column.key}`" :row="row">{{ cellValue(row, column.key) ?? '—' }}</slot>
            </dd>
          </div>
        </dl>
        <div v-if="footerColumns.length" class="ui-cards__footer">
          <slot v-for="column in footerColumns" :key="column.key" :name="`cell-${column.key}`" :row="row">
            {{ cellValue(row, column.key) ?? '—' }}
          </slot>
        </div>
      </li>
    </ul>
  </div>
  <div v-else class="ui-table__wrap">
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
  color: var(--text-muted);
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

.ui-cards__list {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-3);
  list-style: none;
}

.ui-cards__item {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  font-size: 13px;
  color: var(--text);
}

.ui-cards__item--clickable {
  cursor: pointer;
}

.ui-cards__item--clickable:active {
  background: var(--surface-subtle);
}

.ui-cards__item--clickable:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: -2px;
}

.ui-cards__title {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--space-3);
}

.ui-cards__title-item {
  min-width: 0;
}

.ui-cards__title-item:last-child:not(:only-child) {
  flex: 1 1 0;
}

.ui-cards__fields {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.ui-cards__field {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
}

.ui-cards__field dt {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.ui-cards__field dd {
  min-width: 0;
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}

.ui-cards__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border);
}

.ui-cards__footer:not(:has(*)) {
  display: none;
}

.ui-cards__empty {
  padding: var(--space-8) var(--space-4);
  text-align: center;
}
</style>
