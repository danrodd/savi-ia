<script setup lang="ts">
/**
 * Prueba de búsqueda: qué encontraría SAVI en una base y, opcionalmente,
 * para otro usuario. Sirve para verificar permisos antes de que un usuario
 * real pregunte. Usa el mismo índice y la misma política que el chat.
 */
import { ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { companyDocumentService } from '../services/companyDocumentService'
import type { SearchTestResult } from '../types'
import { EXCLUSION_LABELS } from '../utils/companyDocuments'

const props = defineProps<{
  open: boolean
  databases: { id: string; name: string }[]
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const query = ref('')
const databaseId = ref('')
const asLogin = ref('')
const running = ref(false)
const error = ref<string | null>(null)
const result = ref<SearchTestResult | null>(null)

watch(
  () => props.open,
  (open) => {
    if (open && !databaseId.value) databaseId.value = props.databases[0]?.id ?? ''
  },
  { immediate: true },
)

async function onSubmit(): Promise<void> {
  if (!query.value.trim() || !databaseId.value) {
    error.value = 'Escribe una consulta y elige una base.'
    return
  }
  running.value = true
  error.value = null
  try {
    result.value = await companyDocumentService.searchTest(
      query.value.trim(),
      databaseId.value,
      asLogin.value,
    )
  } catch (e) {
    error.value = (e as Error).message || 'No se pudo probar la búsqueda.'
  } finally {
    running.value = false
  }
}
</script>

<template>
  <Dialog :open="open" title="Probar búsqueda" :max-width="680" @update:open="emit('update:open', $event)">
    <form id="document-search-test" class="doctest" novalidate @submit.prevent="onSubmit">
      <label class="doctest__field doctest__field--wide">
        <span class="doctest__label">Consulta</span>
        <input v-model="query" class="doctest__input" maxlength="500" placeholder="¿Cuál es el tope de descuento?" />
      </label>
      <label class="doctest__field">
        <span class="doctest__label">Base</span>
        <select v-model="databaseId" class="doctest__input">
          <option v-for="db in databases" :key="db.id" :value="db.id">{{ db.name }}</option>
        </select>
      </label>
      <label class="doctest__field">
        <span class="doctest__label">Probar como usuario (opcional)</span>
        <input v-model="asLogin" class="doctest__input doctest__input--mono" maxlength="50" placeholder="Código del ERP" />
      </label>
    </form>

    <p v-if="error" class="doctest__error" role="alert">{{ error }}</p>

    <div v-if="result" class="doctest__result" aria-live="polite">
      <p v-if="!result.context.has_access" class="doctest__warning">
        Ese usuario no existe o no está activo en esta base.
      </p>
      <template v-else>
        <p class="doctest__context">
          {{ result.context.login }} ·
          {{ result.context.is_admin ? 'Administrador' : `${result.context.modules.length} módulos` }}
        </p>

        <h3 class="doctest__heading">Encontraría</h3>
        <p v-if="result.results.length === 0" class="doctest__empty">
          Nada relevante. Prueba con otras palabras.
        </p>
        <ul v-else class="doctest__list">
          <li v-for="(hit, i) in result.results" :key="`${hit.document_id}-${i}`" class="doctest__hit">
            <strong>{{ hit.title }}</strong>
            <span v-if="hit.pages" class="doctest__meta"> · p. {{ hit.pages }}</span>
            <span v-if="hit.heading && hit.heading !== hit.title" class="doctest__meta">
              · {{ hit.heading }}</span
            >
            <p class="doctest__snippet">{{ hit.snippet }}</p>
            <p class="doctest__scores">
              similitud {{ hit.vector_score.toFixed(2) }} · coincidencia {{ hit.bm25_score.toFixed(2) }}
            </p>
          </li>
        </ul>

        <template v-if="result.excluded_documents.length > 0">
          <h3 class="doctest__heading">Documentos que este usuario no puede consultar</h3>
          <ul class="doctest__list">
            <li v-for="doc in result.excluded_documents" :key="doc.document_id" class="doctest__excluded">
              {{ doc.title }} — <span class="doctest__meta">{{ EXCLUSION_LABELS[doc.reason] }}</span>
            </li>
          </ul>
        </template>
      </template>
    </div>

    <template #footer>
      <Button variant="ghost" @click="emit('update:open', false)">Cerrar</Button>
      <Button type="submit" form="document-search-test" :loading="running">Probar</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.doctest {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.doctest__field {
  display: grid;
  gap: var(--space-1);
  min-width: 0;
}

.doctest__field--wide {
  grid-column: 1 / -1;
}

.doctest__label,
.doctest__heading {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.doctest__heading {
  margin: var(--space-4) 0 var(--space-2);
}

.doctest__input {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.doctest__input--mono {
  font-family: var(--font-mono, monospace);
}

.doctest__result {
  margin-top: var(--space-4);
}

.doctest__context,
.doctest__empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.doctest__list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.doctest__hit {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 13px;
}

.doctest__meta {
  color: var(--text-muted);
}

.doctest__snippet {
  margin: var(--space-1) 0 0;
  font-size: 12px;
  color: var(--text);
  white-space: pre-line;
}

.doctest__scores {
  margin: var(--space-1) 0 0;
  font-size: 11px;
  color: var(--text-subtle);
}

.doctest__excluded {
  font-size: 13px;
}

.doctest__warning,
.doctest__error {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  font-size: 12px;
}

.doctest__warning {
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
}

.doctest__error {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}

@media (max-width: 560px) {
  .doctest {
    grid-template-columns: 1fr;
  }
}
</style>
