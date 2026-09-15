<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { HttpRequestError } from '@/lib/HttpClient'
import { toast } from '@/lib/toast'
import CompanyDocumentEditDialog from '../components/CompanyDocumentEditDialog.vue'
import CompanyDocumentTable from '../components/CompanyDocumentTable.vue'
import CompanyDocumentUploadDialog from '../components/CompanyDocumentUploadDialog.vue'
import DocumentSearchTestDialog from '../components/DocumentSearchTestDialog.vue'
import { useCompanyDocumentStore } from '../stores/companyDocumentStore'
import { useErpDatabaseStore } from '../stores/erpDatabaseStore'
import type { CompanyDocument } from '../types'
import { ACCEPT_ATTRIBUTE, checkFile, formatBytes } from '../utils/companyDocuments'

const store = useCompanyDocumentStore()
const databaseStore = useErpDatabaseStore()

const uploadOpen = ref(false)
const searchOpen = ref(false)
const editing = ref<CompanyDocument | null>(null)
const removing = ref<CompanyDocument | null>(null)
const replacing = ref<CompanyDocument | null>(null)
const busyId = ref<string | null>(null)
const replaceInput = ref<HTMLInputElement | null>(null)

const databases = computed(() =>
  databaseStore.databases.filter((db) => db.is_active).map((db) => ({ id: db.id, name: db.name })),
)
const databaseNames = computed(() =>
  Object.fromEntries(databaseStore.databases.map((db) => [db.id, db.name])),
)
const usagePercent = computed(() => {
  const usage = store.usage
  if (!usage || usage.chunk_limit === 0) return 0
  return Math.min(100, Math.round((usage.chunks / usage.chunk_limit) * 100))
})

/**
 * La barra solo aparece cuando el número empieza a significar algo. Con 258
 * de 50.000 fragmentos se veía una barra vacía que no decía nada.
 */
const showUsageBar = computed(() => usagePercent.value >= 10)

// Filtros del listado, en el cliente: la lista ya viene entera (hasta 200) y
// filtrar acá responde en cada tecla sin volver a pedir nada al servidor.
const search = ref('')
const statusFilter = ref<'todos' | 'listo' | 'en_proceso' | 'con_problema'>('todos')

const STATUS_GROUPS = {
  listo: ['ready'],
  en_proceso: ['pending', 'processing'],
  con_problema: ['failed', 'no_text'],
} as const

const visibleDocuments = computed(() => {
  const term = search.value.trim().toLowerCase()
  return store.documents.filter((document) => {
    const matchesTerm =
      !term ||
      document.title.toLowerCase().includes(term) ||
      document.original_filename.toLowerCase().includes(term)
    const group = statusFilter.value
    const matchesStatus =
      group === 'todos' ||
      (STATUS_GROUPS[group] as readonly string[]).includes(document.status)
    return matchesTerm && matchesStatus
  })
})

const isFiltering = computed(() => search.value.trim() !== '' || statusFilter.value !== 'todos')

const editOpen = computed({
  get: () => editing.value !== null,
  set: (open: boolean) => {
    if (!open) editing.value = null
  },
})
const removeOpen = computed({
  get: () => removing.value !== null,
  set: (open: boolean) => {
    if (!open) removing.value = null
  },
})

async function withBusy(document: CompanyDocument, action: () => Promise<void>): Promise<void> {
  busyId.value = document.id
  try {
    await action()
  } finally {
    busyId.value = null
  }
}

function onReplace(document: CompanyDocument): void {
  replacing.value = document
  replaceInput.value?.click()
}

async function onReplaceFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const document = replacing.value
  replacing.value = null
  if (!file || !document) return
  const check = checkFile(file)
  if (!check.ok) {
    toast.error(check.reason ?? 'Archivo no válido.')
    return
  }
  await withBusy(document, async () => {
    try {
      await store.replace(document.id, file)
      toast.success(`${document.title}: archivo reemplazado, se está procesando`)
    } catch (e) {
      const duplicate = e instanceof HttpRequestError && e.body.errorCode === 'duplicate_document'
      toast.error(
        duplicate ? 'Ese archivo ya está cargado en otro documento.' : (e as Error).message,
      )
    }
  })
}

function onReprocess(document: CompanyDocument): void {
  void withBusy(document, async () => {
    try {
      await store.reprocess(document.id)
      toast.success(`${document.title} vuelve a procesarse`)
    } catch (e) {
      toast.error((e as Error).message || 'No se pudo reprocesar.')
    }
  })
}

async function onConfirmRemove(): Promise<void> {
  const document = removing.value
  if (!document) return
  await withBusy(document, async () => {
    await store.remove(document.id)
    toast.success(`${document.title} eliminado`)
  })
}

onMounted(() => {
  void databaseStore.load()
  void store.load()
  store.startPolling()
})

onUnmounted(() => store.stopPolling())
</script>

<template>
  <section class="kview">
    <header class="kview__header">
      <div>
        <h1 class="kview__title">Conocimiento de la empresa</h1>
        <p class="kview__subtitle">
          Documentos propios de la empresa —políticas, procedimientos, actas— que SAVI usa para
          responder, citando la fuente y respetando los permisos del ERP.
        </p>
      </div>
      <div class="kview__actions">
        <Button variant="secondary" :disabled="store.documents.length === 0" @click="searchOpen = true">
          Probar búsqueda
        </Button>
        <Button @click="uploadOpen = true">Subir documentos</Button>
      </div>
    </header>

    <div v-if="store.usage" class="kview__usage" aria-label="Uso">
      <span>{{ store.usage.total }} documentos</span>
      <span class="kview__dot">·</span>
      <span>{{ store.usage.chunks.toLocaleString('es-CO') }} de {{ store.usage.chunk_limit.toLocaleString('es-CO') }} fragmentos</span>
      <span
        v-if="showUsageBar"
        class="kview__bar"
        role="progressbar"
        :aria-valuenow="usagePercent"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span class="kview__bar-fill" :style="{ width: `${usagePercent}%` }" />
      </span>
      <span class="kview__dot">·</span>
      <span>{{ formatBytes(store.usage.bytes_stored) }}</span>
    </div>

    <p v-if="store.error" class="kview__error" role="alert">
      {{ store.error }}
      <button type="button" class="kview__retry" @click="store.load()">Reintentar</button>
    </p>
    <p v-else-if="store.loading && store.documents.length === 0" class="kview__hint">Cargando…</p>
    <div v-else-if="store.documents.length === 0" class="kview__empty">
      <p>Aún no hay documentos. Sube el primero para que SAVI pueda consultarlo.</p>
      <!-- El botón acá y no solo arriba: quien llega a una pantalla vacía
           busca la acción en la pantalla vacía. -->
      <Button @click="uploadOpen = true">Subir documentos</Button>
    </div>
    <template v-else>
      <!-- Filtros solo cuando hay suficientes documentos para que sirvan. -->
      <div v-if="store.documents.length > 5" class="kview__filters">
        <input
          v-model="search"
          class="kview__search"
          type="search"
          placeholder="Buscar por nombre…"
          aria-label="Buscar documentos por nombre"
        />
        <select v-model="statusFilter" class="kview__select" aria-label="Filtrar por estado">
          <option value="todos">Todos los estados</option>
          <option value="listo">Listos</option>
          <option value="en_proceso">En proceso</option>
          <option value="con_problema">Con problemas</option>
        </select>
        <span v-if="isFiltering" class="kview__count">
          {{ visibleDocuments.length }} de {{ store.documents.length }}
        </span>
      </div>

      <div v-if="visibleDocuments.length === 0" class="kview__empty">
        <p>Ningún documento coincide con la búsqueda.</p>
      </div>
      <CompanyDocumentTable
        v-else
        :documents="visibleDocuments"
        :database-names="databaseNames"
        :busy-id="busyId"
        @edit="(document) => (editing = document)"
        @replace="onReplace"
        @reprocess="onReprocess"
        @remove="(document) => (removing = document)"
      />
    </template>

    <input
      ref="replaceInput"
      type="file"
      class="kview__file"
      :accept="ACCEPT_ATTRIBUTE"
      aria-label="Elegir archivo de reemplazo"
      @change="onReplaceFile"
    />

    <CompanyDocumentUploadDialog v-model:open="uploadOpen" :databases="databases" />
    <CompanyDocumentEditDialog v-model:open="editOpen" :document="editing" :databases="databases" />
    <DocumentSearchTestDialog v-model:open="searchOpen" :databases="databases" />
    <ConfirmDialog
      v-model:open="removeOpen"
      :title="`Eliminar ${removing?.title ?? ''}`"
      description="Se borra el archivo y deja de usarse de inmediato. Las respuestas anteriores mostrarán la fuente como eliminada."
      confirm-label="Eliminar"
      variant="danger"
      :on-confirm="onConfirmRemove"
    />
  </section>
</template>

<style scoped>
.kview__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.kview__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.kview__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.kview__subtitle {
  margin: 0;
  max-width: 64ch;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted);
}

.kview__usage {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
  font-size: 12px;
  color: var(--text-muted);
}

.kview__dot {
  color: var(--text-subtle);
}

.kview__bar {
  display: inline-block;
  width: 96px;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-subtle);
}

.kview__bar-fill {
  display: block;
  height: 100%;
  background: var(--brand);
}

.kview__hint {
  font-size: 13px;
  color: var(--text-muted);
}

.kview__empty {
  display: grid;
  justify-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-4);
  border: 1px dashed var(--border);
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}

.kview__empty p {
  margin: 0;
}

.kview__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.kview__search,
.kview__select {
  height: 34px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.kview__search {
  flex: 1 1 220px;
  min-width: 0;
}

.kview__count {
  font-size: 12px;
  color: var(--text-muted);
}

.kview__error {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.kview__retry {
  background: transparent;
  border: none;
  color: inherit;
  font: inherit;
  font-weight: var(--fw-semibold);
  text-decoration: underline;
  cursor: pointer;
}

.kview__file {
  display: none;
}
</style>
