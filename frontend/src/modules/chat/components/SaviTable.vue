<script setup lang="ts">
import { computed, ref, useTemplateRef } from 'vue'
import Popover from '@/components/ui/Popover.vue'
import { toCsv } from '@/lib/csv'
import { triggerDownload } from '@/lib/download'

const props = defineProps<{ rows: string[][] }>()

const header = computed(() => props.rows[0] ?? [])
const body = computed(() => props.rows.slice(1))

const trigger = useTemplateRef<HTMLButtonElement>('trigger')
const open = ref(false)

function downloadCsv(): void {
  // BOM (﻿) para que Excel reconozca UTF-8 y no rompa los acentos.
  const blob = new Blob([`﻿${toCsv(props.rows)}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  triggerDownload(url, 'datos.csv')
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

async function downloadXlsx(): Promise<void> {
  // Lazy: SheetJS solo entra al bundle al exportar a Excel. Se usa únicamente
  // para ESCRIBIR (aoa_to_sheet trata los strings como texto, no fórmulas).
  const XLSX = await import('xlsx')
  const ws = XLSX.utils.aoa_to_sheet(props.rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Datos')
  XLSX.writeFile(wb, 'datos.xlsx')
}

function pick(format: 'csv' | 'xlsx'): void {
  open.value = false
  if (format === 'csv') downloadCsv()
  else downloadXlsx()
}
</script>

<template>
  <div class="savi-table" :class="{ 'savi-table--open': open }">
    <div class="savi-table__toolbar">
      <button
        ref="trigger"
        type="button"
        class="savi-table__trigger"
        aria-label="Descargar tabla"
        :aria-expanded="open"
        @click="open = !open"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M12 3v12" />
          <path d="m7 11 5 5 5-5" />
          <path d="M5 21h14" />
        </svg>
        Descargar
      </button>

      <Popover v-model:open="open" :anchor="trigger" side="bottom" align="end" :min-width="150">
        <button type="button" class="menu__item" role="menuitem" @click="pick('csv')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          CSV
        </button>
        <button type="button" class="menu__item" role="menuitem" @click="pick('xlsx')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          Excel
        </button>
      </Popover>
    </div>

    <div class="savi-table__scroll">
      <table>
        <thead>
          <tr>
            <th v-for="(cell, c) in header" :key="c">{{ cell }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, r) in body" :key="r">
            <td v-for="(cell, c) in row" :key="c">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.savi-table {
  margin: 0 0 12px;
}

/* Siempre visible: es el affordance de que la tabla se puede descargar. */
.savi-table__toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-2);
}

.savi-table__trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px var(--space-2) 3px 6px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.savi-table__trigger:hover,
.savi-table--open .savi-table__trigger {
  background: var(--surface-hover);
  color: var(--text);
}

.savi-table__scroll {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  overflow: hidden;
}

th,
td {
  border-bottom: 1px solid var(--border);
  padding: var(--space-3) var(--space-4);
  text-align: left;
}

tr:last-child td {
  border-bottom: none;
}

th {
  background: var(--surface-subtle);
  font-weight: var(--fw-semibold);
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

/* Ítems del menú del popover (mismo lenguaje visual que ConversationMenu). */
.menu__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  font-family: inherit;
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.menu__item:hover,
.menu__item:focus-visible {
  background: var(--surface-subtle);
  outline: none;
}
</style>
