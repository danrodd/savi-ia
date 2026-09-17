<script setup lang="ts">
/**
 * Subida de uno o varios documentos con los mismos permisos.
 *
 * Secuencial a propósito: un error en un archivo no cancela los demás y cada
 * uno muestra su resultado (subido, duplicado o rechazado con el motivo del
 * backend, que es quien valida el contenido real).
 */
import { computed, ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { HttpRequestError } from '@/lib/HttpClient'
import { toast } from '@/lib/toast'
import { useCompanyDocumentStore } from '../stores/companyDocumentStore'
import type { DocumentPermissions } from '../types'
import {
  ACCEPT_ATTRIBUTE,
  checkFile,
  defaultPermissions,
  titleFromFilename,
  validatePermissions,
} from '../utils/companyDocuments'
import CompanyDocumentPermissionsFields from './CompanyDocumentPermissionsFields.vue'

type ItemState = 'queued' | 'uploading' | 'done' | 'duplicate' | 'failed'

interface UploadItem {
  key: string
  file: File
  title: string
  state: ItemState
  message: string | null
}

defineProps<{
  open: boolean
  databases: { id: string; name: string }[]
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const store = useCompanyDocumentStore()
const items = ref<UploadItem[]>([])
const permissions = ref<DocumentPermissions>(defaultPermissions())
const formError = ref<string | null>(null)
const uploading = ref(false)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const finished = computed(
  () =>
    items.value.length > 0 &&
    items.value.every((i) => i.state !== 'queued' && i.state !== 'uploading'),
)
const pendingCount = computed(() => items.value.filter((i) => i.state === 'queued').length)

watch(
  () => items.value.length,
  () => (formError.value = null),
)

function reset(): void {
  items.value = []
  permissions.value = defaultPermissions()
  formError.value = null
}

function close(): void {
  if (uploading.value) return
  emit('update:open', false)
  reset()
}

function addFiles(files: FileList | File[]): void {
  for (const file of Array.from(files)) {
    const check = checkFile(file)
    items.value.push({
      key: `${file.name}-${file.size}-${file.lastModified}-${items.value.length}`,
      file,
      title: titleFromFilename(file.name),
      state: check.ok ? 'queued' : 'failed',
      message: check.ok ? null : (check.reason ?? null),
    })
  }
}

function onInput(event: Event): void {
  const input = event.target as HTMLInputElement
  if (input.files) addFiles(input.files)
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  if (event.dataTransfer?.files) addFiles(event.dataTransfer.files)
}

function onDragLeave(event: DragEvent): void {
  // `dragleave` también salta al pasar por encima de un hijo (el botón, la
  // lista). Sin este chequeo el recuadro parpadea mientras se arrastra.
  const salienteDelFormulario = !(event.currentTarget as HTMLElement).contains(
    event.relatedTarget as Node | null,
  )
  if (salienteDelFormulario) dragging.value = false
}

function removeItem(key: string): void {
  items.value = items.value.filter((i) => i.key !== key)
}

function describeError(error: unknown): { state: ItemState; message: string } {
  if (error instanceof HttpRequestError && error.body.errorCode === 'duplicate_document') {
    const body = error.body as { existing_title?: string }
    return { state: 'duplicate', message: `Ya existe: ${body.existing_title ?? 'otro documento'}.` }
  }
  return { state: 'failed', message: (error as Error).message || 'No se pudo subir.' }
}

async function onSubmit(): Promise<void> {
  formError.value = validatePermissions(permissions.value)
  if (formError.value) return
  if (pendingCount.value === 0) {
    formError.value = 'Agrega al menos un archivo válido.'
    return
  }
  uploading.value = true
  let uploaded = 0
  for (const item of items.value) {
    if (item.state !== 'queued') continue
    item.state = 'uploading'
    try {
      await store.upload(item.file, item.title, permissions.value)
      item.state = 'done'
      item.message = 'Subido. Se está procesando.'
      uploaded++
    } catch (error) {
      Object.assign(item, describeError(error))
    }
  }
  uploading.value = false
  if (uploaded > 0)
    toast.success(uploaded === 1 ? 'Documento subido' : `${uploaded} documentos subidos`)
  // Si todo salió bien no hace falta que el usuario cierre a mano: el
  // toast ya confirma y la lista de atrás ya se actualizó. Si algo quedó
  // duplicado o rechazado, dejamos el modal abierto para que lo vea.
  if (uploaded > 0 && uploaded === items.value.length) close()
}

const STATE_LABELS: Record<ItemState, string> = {
  queued: 'Listo para subir',
  uploading: 'Subiendo…',
  done: 'Subido',
  duplicate: 'Duplicado',
  failed: 'Rechazado',
}
</script>

<template>
  <Dialog
    :open="open"
    title="Subir documentos"
    description="PDF con texto, TXT o Markdown, hasta 20 MB cada uno."
    :max-width="620"
    :close-on-overlay="false"
    @update:open="(value) => (value ? emit('update:open', true) : close())"
  >
    <!-- El `drop` se acepta en TODO el formulario, no solo en la zona
         punteada. Soltar un archivo unos píxeles afuera hacía que el
         navegador lo abriera y se perdiera la pantalla con lo ya cargado:
         un `drop` sin `preventDefault` es una navegación. -->
    <form
      id="company-document-upload"
      class="docup"
      novalidate
      @submit.prevent="onSubmit"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <div class="docup__drop" :class="{ 'docup__drop--active': dragging }">
        <p class="docup__drop-text">Arrastra los archivos acá o</p>
        <Button variant="secondary" size="sm" :disabled="uploading" @click="fileInput?.click()">
          Elegir archivos
        </Button>
        <input
          ref="fileInput"
          type="file"
          multiple
          class="docup__file"
          :accept="ACCEPT_ATTRIBUTE"
          aria-label="Elegir archivos"
          @change="onInput"
        />
      </div>

      <ul v-if="items.length > 0" class="docup__list">
        <li v-for="item in items" :key="item.key" class="docup__item" :class="`docup__item--${item.state}`">
          <div class="docup__item-main">
            <input
              v-model="item.title"
              class="docup__title"
              maxlength="200"
              :disabled="item.state !== 'queued' || uploading"
              :aria-label="`Título de ${item.file.name}`"
            />
            <span class="docup__file-name">{{ item.file.name }}</span>
          </div>
          <div class="docup__item-status">
            <span class="docup__state">{{ STATE_LABELS[item.state] }}</span>
            <span v-if="item.message" class="docup__message">{{ item.message }}</span>
          </div>
          <button
            v-if="item.state === 'queued' && !uploading"
            type="button"
            class="docup__remove"
            :aria-label="`Quitar ${item.file.name}`"
            @click="removeItem(item.key)"
          >
            ×
          </button>
        </li>
      </ul>

      <CompanyDocumentPermissionsFields v-model="permissions" :databases="databases" />

      <p class="docup__notice">
        Cuando un documento sirve para responder, los fragmentos relevantes se envían al proveedor de
        IA configurado, igual que los datos del ERP.
      </p>

      <p v-if="formError" class="docup__error" role="alert">{{ formError }}</p>
    </form>

    <template #footer>
      <Button variant="ghost" :disabled="uploading" @click="close">
        {{ finished ? 'Cerrar' : 'Cancelar' }}
      </Button>
      <Button
        type="submit"
        form="company-document-upload"
        :loading="uploading"
        :disabled="pendingCount === 0"
      >
        Subir {{ pendingCount > 0 ? `(${pendingCount})` : '' }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.docup {
  display: grid;
  gap: var(--space-4);
}

.docup__drop {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-5);
  border: 1px dashed var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
}

.docup__drop--active {
  border-color: var(--brand);
  background: var(--brand-soft);
}

.docup__drop-text {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.docup__file {
  display: none;
}

.docup__list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.docup__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
}

.docup__item-main {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.docup__title {
  height: 30px;
  padding: 0 var(--space-2);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.docup__file-name {
  overflow: hidden;
  font-size: 11px;
  color: var(--text-subtle);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.docup__item-status {
  display: grid;
  justify-items: end;
  font-size: 12px;
  text-align: right;
}

.docup__state {
  font-weight: var(--fw-medium);
  color: var(--text-muted);
}

.docup__message {
  max-width: 24ch;
  color: var(--text-muted);
}

.docup__item--done .docup__state {
  color: var(--text-success, #15803d);
}

.docup__item--duplicate .docup__state,
.docup__item--failed .docup__state,
.docup__item--failed .docup__message {
  color: var(--text-danger, #b91c1c);
}

.docup__remove {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.docup__remove:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.docup__notice {
  margin: 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.4;
}

.docup__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

@media (max-width: 560px) {
  .docup__item {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .docup__item-status {
    grid-column: 1 / -1;
    justify-items: start;
    text-align: left;
  }
}
</style>
