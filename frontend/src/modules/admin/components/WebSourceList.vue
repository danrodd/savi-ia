<script setup lang="ts">
import { FilePen, List, RefreshCw, Trash2 } from 'lucide-vue-next'

import type { RowAction, WebSource } from '../types'
import { visibilityLabel } from '../utils/companyDocuments'
import {
  hostOf,
  isWebInProgress,
  pagesSummary,
  REFRESH_LABELS,
  WEB_STATUS_LABELS,
} from '../utils/webSources'
import CompanyDocumentStatusBadge from './CompanyDocumentStatusBadge.vue'
import RowActionsMenu from './RowActionsMenu.vue'

const props = defineProps<{
  sources: WebSource[]
  databaseNames: Record<string, string>
  busyId: string | null
}>()

const emit = defineEmits<{
  detail: [source: WebSource]
  edit: [source: WebSource]
  refresh: [source: WebSource]
  remove: [source: WebSource]
}>()

const dateFormatter = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function scopeLabel(source: WebSource): string {
  if (source.all_databases) return 'Todas las bases'
  return source.database_ids.map((id) => props.databaseNames[id] ?? 'Base eliminada').join(', ')
}

type SourceAction = 'detail' | 'edit' | 'refresh' | 'remove'

function actionsFor(source: WebSource): RowAction<SourceAction>[] {
  return [
    { id: 'detail', label: 'Ver páginas', icon: List },
    { id: 'edit', label: 'Editar', icon: FilePen },
    {
      id: 'refresh',
      label: 'Leer ahora',
      icon: RefreshCw,
      disabled: isWebInProgress(source.status),
    },
    { id: 'remove', label: 'Eliminar', icon: Trash2, danger: true, divider: true },
  ]
}

function onAction(id: SourceAction, source: WebSource): void {
  if (id === 'detail') emit('detail', source)
  else if (id === 'edit') emit('edit', source)
  else if (id === 'refresh') emit('refresh', source)
  else emit('remove', source)
}

function lastRead(source: WebSource): string {
  if (!source.last_crawl_finished_at) return 'Aún no se ha leído'
  return `Leído ${dateFormatter.format(new Date(source.last_crawl_finished_at))}`
}
</script>

<template>
  <ul class="wlist">
    <li v-for="source in sources" :key="source.id" class="wlist__item">
      <div class="wlist__main">
        <div class="wlist__title">{{ source.title }}</div>
        <a class="wlist__url" :href="source.url" target="_blank" rel="noopener noreferrer">
          {{ source.mode === 'site' ? hostOf(source.url) : source.url }}
        </a>
        <div class="wlist__meta">
          <span>{{ pagesSummary(source) }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ REFRESH_LABELS[source.refresh] }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ visibilityLabel(source) }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ scopeLabel(source) }}</span>
        </div>
      </div>

      <div class="wlist__state">
        <CompanyDocumentStatusBadge
          :label="WEB_STATUS_LABELS[source.status]"
          :message="source.status_message"
        />
        <div class="wlist__sub">{{ lastRead(source) }}</div>
        <div
          v-if="source.status_message"
          class="wlist__sub"
          :class="{ 'wlist__sub--danger': source.status === 'failed' }"
        >
          {{ source.status_message }}
        </div>
      </div>

      <div class="wlist__actions">
        <RowActionsMenu
          :actions="actionsFor(source)"
          :label="`Acciones de ${source.title}`"
          :disabled="busyId === source.id"
          @select="(id) => onAction(id, source)"
        />
      </div>
    </li>
  </ul>
</template>

<style scoped>
.wlist {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.wlist__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: start;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  font-size: 13px;
  color: var(--text);
}

.wlist__title {
  font-weight: var(--fw-medium);
  overflow-wrap: anywhere;
}

.wlist__url {
  display: inline-block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--brand, var(--text));
  overflow-wrap: anywhere;
}

.wlist__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-top: var(--space-1);
  font-size: 12px;
  color: var(--text-muted);
}

.wlist__state {
  display: grid;
  justify-items: start;
  gap: 2px;
  max-width: 32ch;
}

.wlist__sub {
  font-size: 12px;
  color: var(--text-muted);
}

.wlist__sub--danger {
  color: var(--text-danger, #b91c1c);
}

.wlist__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-1);
}

@media (max-width: 720px) {
  .wlist__item {
    grid-template-columns: 1fr;
    gap: var(--space-2);
  }

  .wlist__actions {
    justify-content: flex-end;
  }

}
</style>
