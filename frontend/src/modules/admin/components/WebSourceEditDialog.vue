<script setup lang="ts">
/**
 * Edita nombre, relectura, alcance y permisos de un sitio.
 *
 * - Los permisos aplican de inmediato a todas sus páginas; si pueden dejar
 *   sin acceso a alguien, se pide confirmación, como en los documentos.
 * - El alcance (máximo de páginas, secciones excluidas) solo cambia en la
 *   próxima lectura: al guardarlo se pide una lectura nueva.
 */
import { computed, ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { toast } from '@/lib/toast'
import { useWebSourceStore } from '../stores/webSourceStore'
import type { DocumentPermissions, RefreshFrequency, WebSource } from '../types'
import {
  defaultPermissions,
  narrowsAccess,
  normalizePermissions,
  permissionsOf,
  validatePermissions,
} from '../utils/companyDocuments'
import { REFRESH_LABELS, sectionLabel } from '../utils/webSources'
import CompanyDocumentPermissionsFields from './CompanyDocumentPermissionsFields.vue'

const props = defineProps<{
  open: boolean
  source: WebSource | null
  databases: { id: string; name: string }[]
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const MAX_PAGES_LIMIT = 200

const store = useWebSourceStore()
const title = ref('')
const refresh = ref<RefreshFrequency>('weekly')
const maxPages = ref(MAX_PAGES_LIMIT)
const excluded = ref<string[]>([])
const permissions = ref<DocumentPermissions>(defaultPermissions())
const formError = ref<string | null>(null)
const saving = ref(false)
const confirmingNarrowing = ref(false)

watch(
  () => props.open,
  (open) => {
    if (!open || !props.source) return
    title.value = props.source.title
    refresh.value = props.source.refresh
    maxPages.value = props.source.max_pages
    excluded.value = [...props.source.excluded_sections]
    permissions.value = permissionsOf(props.source)
    formError.value = null
    confirmingNarrowing.value = false
  },
  { immediate: true },
)

watch(permissions, () => (confirmingNarrowing.value = false), { deep: true })

const narrows = computed(
  () =>
    props.source !== null &&
    narrowsAccess(permissionsOf(props.source), normalizePermissions(permissions.value)),
)

const scopeChanged = computed(() => {
  const source = props.source
  if (!source) return false
  const sameSections =
    excluded.value.length === source.excluded_sections.length &&
    excluded.value.every((s) => source.excluded_sections.includes(s))
  return maxPages.value !== source.max_pages || !sameSections
})

function close(): void {
  emit('update:open', false)
}

function include(section: string): void {
  excluded.value = excluded.value.filter((s) => s !== section)
}

async function onSubmit(): Promise<void> {
  const source = props.source
  if (!source) return
  if (!title.value.trim()) {
    formError.value = 'El nombre no puede quedar vacío.'
    return
  }
  if (!Number.isInteger(maxPages.value) || maxPages.value < 1) {
    formError.value = 'El máximo de páginas debe ser un número mayor que cero.'
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
    await store.update(source.id, {
      title: title.value.trim(),
      refresh: refresh.value,
      max_pages: maxPages.value,
      excluded_sections: excluded.value,
      ...normalizePermissions(permissions.value),
    })
    if (scopeChanged.value) {
      try {
        await store.refreshNow(source.id)
        toast.success('Sitio actualizado; se vuelve a leer con el nuevo alcance')
      } catch {
        // 409 si ya se está leyendo: el cambio aplica en la próxima lectura.
        toast.success('Sitio actualizado; el nuevo alcance aplica en la próxima lectura')
      }
    } else {
      toast.success('Sitio actualizado')
    }
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
    title="Editar sitio web"
    :max-width="600"
    :close-on-overlay="false"
    @update:open="emit('update:open', $event)"
  >
    <form id="web-source-edit" class="wedit" novalidate @submit.prevent="onSubmit">
      <label class="wedit__field">
        <span class="wedit__label">Nombre</span>
        <input v-model="title" class="wedit__input" maxlength="200" required />
      </label>

      <div class="wedit__row">
        <label class="wedit__field">
          <span class="wedit__label">Volver a leer</span>
          <select v-model="refresh" class="wedit__input">
            <option v-for="(label, value) in REFRESH_LABELS" :key="value" :value="value">
              {{ label }}
            </option>
          </select>
        </label>
        <label v-if="source?.mode === 'site'" class="wedit__field">
          <span class="wedit__label">Máximo de páginas</span>
          <input
            v-model.number="maxPages"
            class="wedit__input"
            type="number"
            min="1"
            :max="MAX_PAGES_LIMIT"
          />
        </label>
      </div>

      <div v-if="excluded.length" class="wedit__field">
        <span class="wedit__label">Secciones excluidas</span>
        <div class="wedit__chips">
          <span v-for="section in excluded" :key="section" class="wedit__chip" :title="section">
            {{ sectionLabel(section) }}
            <button
              type="button"
              class="wedit__chip-remove"
              :aria-label="`Volver a incluir ${sectionLabel(section)}`"
              @click="include(section)"
            >
              ×
            </button>
          </span>
        </div>
      </div>

      <p v-if="scopeChanged" class="wedit__note">
        Cambiaste el alcance: al guardar, el sitio se vuelve a leer.
      </p>

      <CompanyDocumentPermissionsFields v-model="permissions" :databases="databases" />

      <p v-if="confirmingNarrowing" class="wedit__warning" role="alert">
        Este cambio puede dejar sin acceso a algunos usuarios. Las respuestas que ya citaron este
        sitio se les mostrarán como no disponibles. Presiona Guardar otra vez para confirmar.
      </p>
      <p v-if="formError" class="wedit__error" role="alert">{{ formError }}</p>
    </form>

    <template #footer>
      <Button variant="ghost" :disabled="saving" @click="close">Cancelar</Button>
      <Button
        type="submit"
        form="web-source-edit"
        :variant="confirmingNarrowing ? 'danger' : 'primary'"
        :loading="saving"
      >
        {{ confirmingNarrowing ? 'Confirmar y guardar' : 'Guardar' }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.wedit {
  display: grid;
  gap: var(--space-4);
}

.wedit__row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-3);
}

.wedit__field {
  display: grid;
  gap: var(--space-1);
}

.wedit__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.wedit__input {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.wedit__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.wedit__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.wedit__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-1) 2px var(--space-2);
  border-radius: 999px;
  background: var(--surface-subtle);
  font-size: 12px;
}

.wedit__chip-remove {
  padding: 0 4px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font: inherit;
  cursor: pointer;
}

.wedit__chip-remove:hover {
  color: var(--text);
}

.wedit__note {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.wedit__warning,
.wedit__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  font-size: 12px;
  line-height: 1.5;
}

.wedit__warning {
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
}

.wedit__error {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}
</style>
