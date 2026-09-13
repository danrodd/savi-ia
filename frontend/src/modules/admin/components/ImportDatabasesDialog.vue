<script setup lang="ts">
/**
 * Importa un archivo exportado desde otra instalación de SAVI. Por
 * código: crea las bases que no existen acá y actualiza las que sí
 * (host, usuario, contraseña, timeout) — así varios agentes convergen a
 * la misma configuración. Es best-effort por fila: si esta máquina no
 * alcanza algún cliente por red, esa fila queda `failed` y el resto se
 * importa igual.
 */
import { ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { toast } from '@/lib/toast'
import { erpDatabaseService } from '../services/erpDatabaseService'
import { useErpDatabaseStore } from '../stores/erpDatabaseStore'
import type { ExportedErpDatabasesFile, ImportRowResult } from '../types'

const open = defineModel<boolean>('open', { required: true })

const store = useErpDatabaseStore()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<ExportedErpDatabasesFile | null>(null)
const fileName = ref('')
const passphrase = ref('')
const error = ref<string | null>(null)
const importing = ref(false)
const results = ref<ImportRowResult[] | null>(null)

const STATUS_LABELS: Record<ImportRowResult['status'], string> = {
  created: 'Creada',
  updated: 'Actualizada',
  failed: 'No se pudo',
}

watch(open, (value) => {
  if (value) {
    selectedFile.value = null
    fileName.value = ''
    passphrase.value = ''
    error.value = null
    results.value = null
  }
})

async function onFileChange(event: Event): Promise<void> {
  error.value = null
  results.value = null
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  fileName.value = file.name
  try {
    const parsed = JSON.parse(await file.text()) as Partial<ExportedErpDatabasesFile>
    if (typeof parsed.payload !== 'string' || typeof parsed.version !== 'number') {
      throw new Error('formato inválido')
    }
    selectedFile.value = parsed as ExportedErpDatabasesFile
  } catch {
    selectedFile.value = null
    error.value = 'El archivo no parece ser una exportación válida de SAVI.'
  }
}

async function onImport(): Promise<void> {
  if (!selectedFile.value) {
    error.value = 'Elegí el archivo exportado.'
    return
  }
  if (!passphrase.value) {
    error.value = 'La contraseña es obligatoria.'
    return
  }
  error.value = null
  importing.value = true
  try {
    const result = await erpDatabaseService.import(passphrase.value, selectedFile.value.payload)
    results.value = result.rows
    await store.load()
    const failed = result.rows.filter((r) => r.status === 'failed').length
    if (failed === 0) {
      toast.success(`${result.rows.length} base${result.rows.length === 1 ? '' : 's'} importada${result.rows.length === 1 ? '' : 's'}`)
    } else {
      toast.info(`${failed} de ${result.rows.length} no se pudieron importar — revisá el detalle`)
    }
  } catch (e) {
    error.value = (e as Error).message || 'No se pudo importar el archivo.'
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <Dialog
    :open="open"
    title="Importar bases de datos"
    description="Cargá un archivo exportado desde otra instalación de SAVI. Las bases con el mismo código se actualizan; el resto se crea."
    :max-width="520"
    @update:open="open = $event"
  >
    <form class="importform" novalidate @submit.prevent="onImport">
      <label class="importform__field">
        <span class="importform__label">Archivo</span>
        <input
          ref="fileInput"
          type="file"
          accept="application/json,.json"
          class="importform__file"
          @change="onFileChange"
        />
        <span v-if="fileName" class="importform__hint">{{ fileName }}</span>
      </label>
      <label class="importform__field">
        <span class="importform__label">Contraseña del archivo</span>
        <input
          v-model="passphrase"
          type="password"
          class="importform__input"
          autocomplete="off"
        />
      </label>

      <p v-if="error" class="importform__error" role="alert">{{ error }}</p>

      <div v-if="results" class="importform__results">
        <table class="importform__table">
          <thead>
            <tr>
              <th scope="col">Código</th>
              <th scope="col">Resultado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in results" :key="row.code">
              <td class="importform__code">{{ row.code }}</td>
              <td>
                <span
                  class="importform__status"
                  :class="`importform__status--${row.status}`"
                >
                  {{ STATUS_LABELS[row.status] }}
                </span>
                <span v-if="row.detail" class="importform__detail">{{ row.detail }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </form>

    <template #footer>
      <Button variant="ghost" :disabled="importing" @click="open = false">
        {{ results ? 'Cerrar' : 'Cancelar' }}
      </Button>
      <Button v-if="!results" :loading="importing" @click="onImport">Importar</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.importform {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.importform__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.importform__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.importform__input,
.importform__file {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.importform__file {
  padding: var(--space-1) var(--space-2);
}

.importform__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.importform__hint {
  font-size: 11px;
  color: var(--text-subtle);
}

.importform__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.importform__results {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.importform__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.importform__table th {
  position: sticky;
  top: 0;
  padding: var(--space-2) var(--space-3);
  text-align: left;
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-subtle);
  background: var(--surface-elev);
  border-bottom: 1px solid var(--border);
}

.importform__table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.importform__table tbody tr:last-child td {
  border-bottom: none;
}

.importform__code {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}

.importform__status {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: 11px;
  font-weight: var(--fw-medium);
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.importform__status--created,
.importform__status--updated {
  background: var(--surface-success, rgba(22, 163, 74, 0.1));
  color: var(--text-success, #15803d);
}

.importform__status--failed {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}

.importform__detail {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-subtle);
}
</style>
