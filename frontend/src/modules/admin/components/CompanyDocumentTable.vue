<script setup lang="ts">
import type { CompanyDocument } from '../types'
import { formatBytes, isInProgress, visibilityLabel } from '../utils/companyDocuments'
import CompanyDocumentStatusBadge from './CompanyDocumentStatusBadge.vue'

const props = defineProps<{
  documents: CompanyDocument[]
  databaseNames: Record<string, string>
  busyId: string | null
}>()

const emit = defineEmits<{
  edit: [document: CompanyDocument]
  replace: [document: CompanyDocument]
  reprocess: [document: CompanyDocument]
  remove: [document: CompanyDocument]
}>()

const dateFormatter = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function scopeLabel(document: CompanyDocument): string {
  if (document.all_databases) return 'Todas'
  return document.database_ids.map((id) => props.databaseNames[id] ?? 'Base eliminada').join(', ')
}

function detail(document: CompanyDocument): string {
  const parts = [formatBytes(document.size_bytes)]
  if (document.page_count) parts.push(`${document.page_count} pág.`)
  if (document.version > 1) parts.push(`versión ${document.version}`)
  return parts.join(' · ')
}
</script>

<template>
  <div class="dbtable__wrap">
    <table class="dbtable">
      <thead>
        <tr>
          <th scope="col">Documento</th>
          <th scope="col">Quién lo ve</th>
          <th scope="col">Bases</th>
          <th scope="col">Estado</th>
          <th scope="col">Actualizado</th>
          <th scope="col"><span class="dbtable__sr">Acciones</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="document in documents" :key="document.id">
          <td>
            <div class="dbtable__name">{{ document.title }}</div>
            <div class="dbtable__sub">{{ detail(document) }}</div>
          </td>
          <td>{{ visibilityLabel(document) }}</td>
          <td class="dbtable__sub">{{ scopeLabel(document) }}</td>
          <td>
            <CompanyDocumentStatusBadge :status="document.status" :message="document.status_message" />
            <div v-if="document.status_message" class="dbtable__sub dbtable__sub--danger">
              {{ document.status_message }}
            </div>
          </td>
          <td class="dbtable__sub">{{ dateFormatter.format(new Date(document.updated_at)) }}</td>
          <td>
            <div class="dbtable__actions">
              <button
                type="button"
                class="dbtable__action"
                :disabled="busyId === document.id"
                @click="emit('edit', document)"
              >
                Editar
              </button>
              <button
                type="button"
                class="dbtable__action"
                :disabled="busyId === document.id"
                @click="emit('replace', document)"
              >
                Reemplazar
              </button>
              <button
                v-if="document.status === 'failed' || document.status === 'no_text'"
                type="button"
                class="dbtable__action"
                :disabled="busyId === document.id || isInProgress(document.status)"
                @click="emit('reprocess', document)"
              >
                Reprocesar
              </button>
              <button
                type="button"
                class="dbtable__action dbtable__action--danger"
                :disabled="busyId === document.id"
                @click="emit('remove', document)"
              >
                Eliminar
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.dbtable__wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
}

.dbtable {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: var(--text);
}

.dbtable th {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.dbtable td {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.dbtable tbody tr:last-child td {
  border-bottom: none;
}

.dbtable__name {
  font-weight: var(--fw-medium);
  overflow-wrap: anywhere;
}

.dbtable__sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.dbtable__sub--danger {
  max-width: 32ch;
  color: var(--text-danger, #b91c1c);
}

.dbtable__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-1);
}

.dbtable__action {
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  white-space: nowrap;
}

.dbtable__action:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text);
}

.dbtable__action--danger:hover:not(:disabled) {
  color: var(--text-danger, #b91c1c);
}

.dbtable__action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.dbtable__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
