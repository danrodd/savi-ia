<script setup lang="ts">
/**
 * Exporta las bases activas a un archivo `.json` para cargarlas en otra
 * instalación (ej. otro agente del call center). El archivo queda
 * cifrado con la contraseña que se ingresa acá — no con la clave interna
 * de esta instalación — así que quien lo reciba necesita esa misma
 * contraseña para poder importarlo.
 */
import { ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { triggerDownload } from '@/lib/download'
import { toast } from '@/lib/toast'
import { erpDatabaseService } from '../services/erpDatabaseService'

const open = defineModel<boolean>('open', { required: true })

const passphrase = ref('')
const confirmPassphrase = ref('')
const error = ref<string | null>(null)
const exporting = ref(false)

watch(open, (value) => {
  if (value) {
    passphrase.value = ''
    confirmPassphrase.value = ''
    error.value = null
  }
})

async function onExport(): Promise<void> {
  if (passphrase.value.length < 8) {
    error.value = 'La contraseña debe tener al menos 8 caracteres.'
    return
  }
  if (passphrase.value !== confirmPassphrase.value) {
    error.value = 'Las contraseñas no coinciden.'
    return
  }
  error.value = null
  exporting.value = true
  try {
    const file = await erpDatabaseService.export(passphrase.value)
    const blob = new Blob([JSON.stringify(file, null, 2)], { type: 'application/json' })
    const date = file.exported_at.slice(0, 10)
    triggerDownload(URL.createObjectURL(blob), `savi-bases-erp-${date}.json`)
    toast.success(`${file.count} base${file.count === 1 ? '' : 's'} exportada${file.count === 1 ? '' : 's'}`, {
      description: 'Compartí el archivo y la contraseña por separado.',
    })
    open.value = false
  } catch (e) {
    error.value = (e as Error).message || 'No se pudo exportar.'
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <Dialog
    :open="open"
    title="Exportar bases de datos"
    description="Descarga un archivo con las bases activas para cargarlo en otra instalación de SAVI (por ejemplo, la de otro agente)."
    :max-width="440"
    @update:open="open = $event"
  >
    <form class="exportform" novalidate @submit.prevent="onExport">
      <label class="exportform__field">
        <span class="exportform__label">Contraseña del archivo</span>
        <input
          v-model="passphrase"
          type="password"
          class="exportform__input"
          autocomplete="new-password"
          minlength="8"
        />
      </label>
      <label class="exportform__field">
        <span class="exportform__label">Repetir contraseña</span>
        <input
          v-model="confirmPassphrase"
          type="password"
          class="exportform__input"
          autocomplete="new-password"
        />
      </label>
      <p class="exportform__hint">
        Quien reciba el archivo va a necesitar esta misma contraseña para importarlo.
        Compartíla por un canal distinto al del archivo.
      </p>
      <p v-if="error" class="exportform__error" role="alert">{{ error }}</p>
    </form>

    <template #footer>
      <Button variant="ghost" :disabled="exporting" @click="open = false">Cancelar</Button>
      <Button :loading="exporting" @click="onExport">Exportar</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.exportform {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.exportform__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.exportform__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.exportform__input {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.exportform__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.exportform__hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.5;
}

.exportform__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}
</style>
