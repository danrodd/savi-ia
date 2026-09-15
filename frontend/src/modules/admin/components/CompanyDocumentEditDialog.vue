<script setup lang="ts">
/**
 * Edita título y permisos. No reprocesa: aplica en la siguiente pregunta.
 * Si el cambio puede dejar sin acceso a alguien, pide confirmación antes.
 */
import { computed, ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { toast } from '@/lib/toast'
import { useCompanyDocumentStore } from '../stores/companyDocumentStore'
import type { CompanyDocument, DocumentPermissions } from '../types'
import {
  narrowsAccess,
  normalizePermissions,
  permissionsOf,
  validatePermissions,
} from '../utils/companyDocuments'
import CompanyDocumentPermissionsFields from './CompanyDocumentPermissionsFields.vue'

const props = defineProps<{
  open: boolean
  document: CompanyDocument | null
  databases: { id: string; name: string }[]
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const store = useCompanyDocumentStore()
const title = ref('')
const permissions = ref<DocumentPermissions>({
  visibility: 'all',
  modules: [],
  all_databases: true,
  database_ids: [],
})
const formError = ref<string | null>(null)
const saving = ref(false)
const confirmingNarrowing = ref(false)

watch(
  () => props.open,
  (open) => {
    if (!open || !props.document) return
    title.value = props.document.title
    permissions.value = permissionsOf(props.document)
    formError.value = null
    confirmingNarrowing.value = false
  },
  { immediate: true },
)

// Cualquier cambio posterior invalida la confirmación: se confirma lo que se ve.
watch(permissions, () => (confirmingNarrowing.value = false), { deep: true })

const narrows = computed(
  () =>
    props.document !== null &&
    narrowsAccess(permissionsOf(props.document), normalizePermissions(permissions.value)),
)

function close(): void {
  emit('update:open', false)
}

async function onSubmit(): Promise<void> {
  if (!props.document) return
  if (!title.value.trim()) {
    formError.value = 'El título no puede quedar vacío.'
    return
  }
  formError.value = validatePermissions(permissions.value)
  if (formError.value) return
  if (narrows.value && !confirmingNarrowing.value) {
    confirmingNarrowing.value = true
    return
  }
  saving.value = true
  try {
    await store.update(props.document.id, {
      title: title.value.trim(),
      ...normalizePermissions(permissions.value),
    })
    toast.success('Documento actualizado')
    close()
  } catch (e) {
    formError.value = (e as Error).message || 'No se pudo guardar.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    :open="open"
    title="Editar documento"
    :max-width="600"
    :close-on-overlay="false"
    @update:open="emit('update:open', $event)"
  >
    <form id="company-document-edit" class="docedit" novalidate @submit.prevent="onSubmit">
      <label class="docedit__field">
        <span class="docedit__label">Título</span>
        <input v-model="title" class="docedit__input" maxlength="200" required />
      </label>

      <CompanyDocumentPermissionsFields v-model="permissions" :databases="databases" />

      <p v-if="confirmingNarrowing" class="docedit__warning" role="alert">
        Este cambio puede dejar sin acceso a algunos usuarios. Las respuestas que ya citaron este
        documento se les mostrarán como no disponibles. Presiona Guardar otra vez para confirmar.
      </p>
      <p v-if="formError" class="docedit__error" role="alert">{{ formError }}</p>
    </form>

    <template #footer>
      <Button variant="ghost" :disabled="saving" @click="close">Cancelar</Button>
      <Button
        type="submit"
        form="company-document-edit"
        :variant="confirmingNarrowing ? 'danger' : 'primary'"
        :loading="saving"
      >
        {{ confirmingNarrowing ? 'Confirmar y guardar' : 'Guardar' }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.docedit {
  display: grid;
  gap: var(--space-4);
}

.docedit__field {
  display: grid;
  gap: var(--space-1);
}

.docedit__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.docedit__input {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.docedit__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.docedit__warning,
.docedit__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  font-size: 12px;
  line-height: 1.5;
}

.docedit__warning {
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
}

.docedit__error {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}
</style>
