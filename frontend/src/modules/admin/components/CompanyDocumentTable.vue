<script setup lang="ts">
import type { CompanyDocument } from '../types'
import { canReadWithAi, progressLabel, READING_LABELS, readingDetail } from '../utils/aiReading'
import { formatBytes, isInProgress, visibilityLabel } from '../utils/companyDocuments'
import CompanyDocumentStatusBadge from './CompanyDocumentStatusBadge.vue'

const props = defineProps<{
  documents: CompanyDocument[]
  databaseNames: Record<string, string>
  busyId: string | null
  /** La lectura con IA está activa y hay proveedor: se ofrece "Leer con IA". */
  aiReadingAvailable: boolean
}>()

const emit = defineEmits<{
  edit: [document: CompanyDocument]
  replace: [document: CompanyDocument]
  reprocess: [document: CompanyDocument]
  readWithAi: [document: CompanyDocument]
  remove: [document: CompanyDocument]
}>()

const dateFormatter = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function scopeLabel(document: CompanyDocument): string {
  if (document.all_databases) return 'Todas'
  return document.database_ids.map((id) => props.databaseNames[id] ?? 'Base eliminada').join(', ')
}

function progressOf(
  document: CompanyDocument,
): { done: number; total: number; percent: number } | null {
  const { progress_done: done, progress_total: total } = document
  // `== null` a propósito: atrapa `null` **y** `undefined`. Con `=== null`,
  // una respuesta que no traiga los campos (un backend viejo detrás de un
  // frontend nuevo) pasaba el filtro y dibujaba una barra vacía en
  // documentos ya terminados.
  if (done == null || total == null || total <= 0) return null
  return { done, total, percent: Math.min(100, Math.round((done * 100) / total)) }
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
            <span
              v-if="document.reading_method"
              class="dbtable__tag"
              :class="`dbtable__tag--${document.reading_method}`"
              :title="readingDetail(document) ?? undefined"
            >
              Leído con {{ READING_LABELS[document.reading_method] }}
            </span>
          </td>
          <td data-label="Quién lo ve">{{ visibilityLabel(document) }}</td>
          <td class="dbtable__sub" data-label="Bases">{{ scopeLabel(document) }}</td>
          <td>
            <CompanyDocumentStatusBadge :status="document.status" :message="document.status_message" />
            <!-- Un PDF de 500 páginas tarda casi dos minutos: sin esto el
                 estado decía solo "Procesando…" y no se sabía si avanzaba. -->
            <div v-if="progressOf(document)" class="dbtable__progress">
              <span class="dbtable__progress-bar">
                <span
                  class="dbtable__progress-fill"
                  :style="{ width: `${progressOf(document)?.percent ?? 0}%` }"
                />
              </span>
              <span class="dbtable__sub">
                {{
                  progressLabel(document) ??
                  `${progressOf(document)?.done} de ${progressOf(document)?.total} fragmentos`
                }}
              </span>
            </div>
            <div v-if="document.status_message" class="dbtable__sub dbtable__sub--danger">
              {{ document.status_message }}
            </div>
          </td>
          <td class="dbtable__sub" data-label="Actualizado">
            {{ dateFormatter.format(new Date(document.updated_at)) }}
          </td>
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
              <!-- Destacado en "Sin texto": es justo el caso que la IA resuelve. -->
              <button
                v-if="aiReadingAvailable && canReadWithAi(document)"
                type="button"
                class="dbtable__action"
                :class="{ 'dbtable__action--primary': document.status === 'no_text' }"
                :disabled="busyId === document.id"
                @click="emit('readWithAi', document)"
              >
                Leer con IA
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

.dbtable__tag {
  display: inline-block;
  margin-top: var(--space-1);
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--surface-subtle);
}

.dbtable__progress {
  display: grid;
  gap: 2px;
  margin-top: var(--space-1);
  max-width: 160px;
}

.dbtable__progress-bar {
  display: block;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-subtle);
}

.dbtable__progress-fill {
  display: block;
  height: 100%;
  background: var(--brand);
  transition: width var(--duration-slow, 320ms) var(--ease-out, ease-out);
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

.dbtable__action--primary {
  border-color: var(--brand-ring, var(--border));
  color: var(--brand, var(--text));
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

/* En pantallas angostas la tabla pasa a tarjetas.
   Con scroll horizontal, las acciones (Editar, Reemplazar, Eliminar) quedaban
   fuera de la pantalla y no había señal de que estuvieran ahí: en un teléfono
   la fila se veía como si fuera de solo lectura. */
@media (max-width: 720px) {
  .dbtable__wrap {
    overflow-x: visible;
    border: none;
    background: transparent;
  }

  .dbtable,
  .dbtable tbody,
  .dbtable tr,
  .dbtable td {
    display: block;
    width: 100%;
  }

  .dbtable thead {
    display: none;
  }

  .dbtable tbody tr {
    margin-bottom: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    background: var(--surface-elev);
  }

  .dbtable td {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
  }

  /* Encabezado de la celda, tomado de `data-label`: sin la fila de títulos
     de la tabla, "Todas" o una fecha suelta no dicen nada. */
  .dbtable td[data-label]::before {
    content: attr(data-label);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-subtle);
  }

  .dbtable tbody tr td:last-child {
    border-bottom: none;
  }

  .dbtable__actions {
    justify-content: flex-start;
    width: 100%;
  }

  .dbtable__action {
    border-color: var(--border);
    padding: var(--space-1) var(--space-3);
  }

  .dbtable__progress {
    max-width: none;
  }
}
</style>
