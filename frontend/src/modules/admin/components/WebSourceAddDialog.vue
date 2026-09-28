<script setup lang="ts">
/**
 * Agrega un sitio o una página en dos pasos:
 * 1. La dirección y el alcance.
 * 2. La vista previa (páginas encontradas, avisos, muestra del texto) para
 *    excluir secciones y elegir permisos antes de guardar.
 *
 * Cambiar la dirección o el alcance descarta la vista previa: se guarda lo
 * que se revisó.
 */
import { computed, ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { toast } from '@/lib/toast'
import { useWebSourceStore } from '../stores/webSourceStore'
import type {
  DocumentPermissions,
  RefreshFrequency,
  WebSourceMode,
  WebSourcePreview,
} from '../types'
import { defaultPermissions, validatePermissions } from '../utils/companyDocuments'
import {
  estimatePages,
  isValidUrlInput,
  normalizeUrlInput,
  REFRESH_LABELS,
  sectionLabel,
} from '../utils/webSources'
import CompanyDocumentPermissionsFields from './CompanyDocumentPermissionsFields.vue'

const props = defineProps<{
  open: boolean
  databases: { id: string; name: string }[]
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const DEFAULT_MAX_PAGES = 200

const store = useWebSourceStore()
const url = ref('')
const mode = ref<WebSourceMode>('site')
const maxPages = ref(DEFAULT_MAX_PAGES)
const preview = ref<WebSourcePreview | null>(null)
const title = ref('')
const refresh = ref<RefreshFrequency>('weekly')
const excluded = ref<string[]>([])
const permissions = ref<DocumentPermissions>(defaultPermissions())
const formError = ref<string | null>(null)
const previewing = ref(false)
const saving = ref(false)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    url.value = ''
    mode.value = 'site'
    maxPages.value = DEFAULT_MAX_PAGES
    preview.value = null
    title.value = ''
    refresh.value = 'weekly'
    excluded.value = []
    permissions.value = defaultPermissions()
    formError.value = null
  },
  { immediate: true },
)

watch([url, mode, maxPages], () => {
  preview.value = null
  excluded.value = []
})

const sections = computed(() =>
  Object.entries(preview.value?.sections ?? {}).sort(([, a], [, b]) => b - a),
)
const pagesToRead = computed(() =>
  preview.value
    ? estimatePages(preview.value.page_count, preview.value.sections, excluded.value)
    : 0,
)

function close(): void {
  emit('update:open', false)
}

function toggleSection(name: string): void {
  excluded.value = excluded.value.includes(name)
    ? excluded.value.filter((s) => s !== name)
    : [...excluded.value, name]
}

async function onPreview(): Promise<void> {
  if (!isValidUrlInput(url.value)) {
    formError.value = 'Escribe una dirección web válida, por ejemplo www.empresa.com.'
    return
  }
  formError.value = null
  previewing.value = true
  try {
    const result = await store.preview({
      url: normalizeUrlInput(url.value),
      mode: mode.value,
      max_pages: maxPages.value,
      excluded_sections: [],
    })
    preview.value = result
    title.value = result.title
  } catch (e) {
    formError.value = (e as Error).message || 'No se pudo revisar la dirección.'
  } finally {
    previewing.value = false
  }
}

async function onSubmit(): Promise<void> {
  if (!preview.value) {
    await onPreview()
    return
  }
  formError.value = validatePermissions(permissions.value)
  if (formError.value) return
  if (
    mode.value === 'site' &&
    excluded.value.length > 0 &&
    excluded.value.length === sections.value.length
  ) {
    formError.value = 'Dejaste todas las secciones fuera: elige al menos una.'
    return
  }
  saving.value = true
  try {
    const created = await store.create({
      url: preview.value.url,
      mode: mode.value,
      title: title.value.trim() || undefined,
      refresh: refresh.value,
      max_pages: maxPages.value,
      excluded_sections: excluded.value,
      ...permissions.value,
    })
    toast.success(`${created.title}: se está leyendo`)
    close()
  } catch (e) {
    formError.value = (e as Error).message || 'No se pudo agregar.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    :open="open"
    title="Agregar sitio o página"
    description="SAVI lee el texto público de la dirección y lo usa para responder, citando el link."
    :max-width="640"
    :close-on-overlay="false"
    @update:open="emit('update:open', $event)"
  >
    <form id="web-source-add" class="wadd" novalidate @submit.prevent="onSubmit">
      <label class="wadd__field">
        <span class="wadd__label">Dirección</span>
        <input
          v-model="url"
          class="wadd__input"
          type="url"
          inputmode="url"
          placeholder="www.empresa.com"
          maxlength="2048"
          required
        />
      </label>

      <fieldset class="wadd__fieldset">
        <legend class="wadd__label">Qué leer</legend>
        <label class="wadd__radio">
          <input v-model="mode" type="radio" value="site" />
          <span>
            <strong>Todo el sitio</strong>
            <span class="wadd__hint">La dirección y las páginas del mismo sitio.</span>
          </span>
        </label>
        <label class="wadd__radio">
          <input v-model="mode" type="radio" value="page" />
          <span>
            <strong>Solo esta página</strong>
            <span class="wadd__hint">Útil para una página de precios o de políticas.</span>
          </span>
        </label>
      </fieldset>

      <label v-if="mode === 'site'" class="wadd__field wadd__field--inline">
        <span class="wadd__label">Máximo de páginas</span>
        <input
          v-model.number="maxPages"
          class="wadd__input wadd__input--short"
          type="number"
          min="1"
          :max="DEFAULT_MAX_PAGES"
        />
      </label>

      <template v-if="preview">
        <section class="wadd__preview" aria-label="Vista previa">
          <p class="wadd__summary">
            <template v-if="mode === 'site'">
              <template v-if="excluded.length">
                Se leerán unas <strong>{{ pagesToRead }}</strong> de las
                {{ preview.page_count }} páginas encontradas
              </template>
              <template v-else>
                Se leerán <strong>{{ preview.page_count }}</strong> páginas encontradas
              </template>
              {{ preview.used_sitemap ? 'en el mapa del sitio' : 'siguiendo los enlaces' }}.
            </template>
            <template v-else>Se leerá la página ({{ preview.words }} palabras).</template>
          </p>

          <ul v-if="preview.warnings.length" class="wadd__warnings">
            <li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li>
          </ul>

          <fieldset v-if="mode === 'site' && sections.length > 1" class="wadd__fieldset">
            <legend class="wadd__label">Secciones</legend>
            <p class="wadd__hint">Desmarca las que no aportan, como el blog o las etiquetas.</p>
            <div class="wadd__sections">
              <label v-for="[name, count] in sections" :key="name" class="wadd__check" :title="name">
                <input
                  type="checkbox"
                  :checked="!excluded.includes(name)"
                  @change="toggleSection(name)"
                />
                <span>{{ sectionLabel(name) }}</span>
                <span class="wadd__count">{{ count }}</span>
              </label>
            </div>
          </fieldset>

          <details class="wadd__sample">
            <summary>Texto leído de la primera página</summary>
            <pre>{{ preview.sample || 'La página no tiene texto legible.' }}</pre>
          </details>
        </section>

        <label class="wadd__field">
          <span class="wadd__label">Nombre</span>
          <input v-model="title" class="wadd__input" maxlength="200" />
        </label>

        <label class="wadd__field wadd__field--inline">
          <span class="wadd__label">Volver a leer</span>
          <select v-model="refresh" class="wadd__input wadd__input--short">
            <option v-for="(label, value) in REFRESH_LABELS" :key="value" :value="value">
              {{ label }}
            </option>
          </select>
        </label>

        <CompanyDocumentPermissionsFields v-model="permissions" :databases="databases" />
      </template>

      <p v-if="previewing" class="wadd__hint" role="status">
        Buscando las páginas del sitio y leyendo la primera; puede tardar unos segundos.
      </p>
      <p v-if="formError" class="wadd__error" role="alert">{{ formError }}</p>
    </form>

    <template #footer>
      <Button variant="ghost" :disabled="saving || previewing" @click="close">Cancelar</Button>
      <Button type="submit" form="web-source-add" :loading="previewing || saving">
        {{ preview ? 'Agregar' : previewing ? 'Revisando…' : 'Revisar' }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.wadd {
  display: grid;
  gap: var(--space-4);
}

.wadd__field {
  display: grid;
  gap: var(--space-1);
}

.wadd__field--inline {
  grid-template-columns: auto auto;
  justify-content: start;
  align-items: center;
  gap: var(--space-3);
}

/* Casillas y radios con el color de la marca, como en los permisos. */
.wadd input[type='checkbox'],
.wadd input[type='radio'] {
  accent-color: var(--brand);
}

.wadd__fieldset {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: none;
}

.wadd__label {
  padding: 0;
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.wadd__input {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.wadd__input--short {
  width: 140px;
}

.wadd__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.wadd__radio {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: 13px;
  cursor: pointer;
}

.wadd__radio > span {
  display: grid;
}

.wadd__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.wadd__preview {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
}

.wadd__summary {
  margin: 0;
  font-size: 13px;
}

.wadd__warnings {
  margin: 0;
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-6);
  border-radius: var(--r-sm);
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
  font-size: 12px;
  line-height: 1.5;
}

.wadd__sections {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-1) var(--space-3);
}

.wadd__check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 13px;
  cursor: pointer;
}

.wadd__count {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-muted);
}

.wadd__sample summary {
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
}

.wadd__sample pre {
  max-height: 180px;
  margin: var(--space-2) 0 0;
  padding: var(--space-2);
  overflow: auto;
  border-radius: var(--r-sm);
  background: var(--surface-elev);
  font-family: inherit;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.wadd__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
  line-height: 1.5;
}
</style>
