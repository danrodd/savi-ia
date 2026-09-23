<script setup lang="ts">
/**
 * Selector del cliente (base del ERP) para una conversación nueva.
 *
 * Es un combo con búsqueda: soporte atiende a muchos clientes y con una
 * lista larga hay que poder escribir parte del código o del nombre.
 *
 * El modelo vale `null` para "la base de la sesión" (así lo entiende el
 * backend: sin `erp_database_id`, usa la base de login). Esa base aparece
 * UNA sola vez, primera y marcada "tu sesión"; antes figuraba dos veces,
 * como "Base con la que iniciaste sesión" y otra vez con su nombre.
 */
import {
  ComboboxAnchor,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxPortal,
  ComboboxRoot,
  ComboboxTrigger,
  ComboboxViewport,
} from 'reka-ui'
import { computed, ref } from 'vue'

import type { AvailableErpDatabase } from '@/modules/admin'
import { filterDatabases, sortWithSessionFirst } from '../utils/databaseSearch'

const props = defineProps<{
  databases: AvailableErpDatabase[]
  /** Base de login. `null` si la sesión es anterior a que el backend la informe. */
  sessionDatabaseId?: string | null
}>()

const selected = defineModel<string | null>({ required: true })

// Valor interno cuando la base de la sesión no está en la lista (sesión
// vieja sin `erp_database`): se ofrece igual, con el texto genérico.
const SESSION = '__session__'

const search = ref('')

const sessionInList = computed(
  () => !!props.sessionDatabaseId && props.databases.some((d) => d.id === props.sessionDatabaseId),
)

const options = computed(() => {
  const sorted = sortWithSessionFirst(props.databases, props.sessionDatabaseId ?? null)
  const items = sorted.map((db) => ({
    value: db.id === props.sessionDatabaseId ? SESSION : db.id,
    label: db.name,
    code: db.code,
    isSession: db.id === props.sessionDatabaseId,
  }))
  if (!sessionInList.value) {
    items.unshift({
      value: SESSION,
      label: 'Base con la que iniciaste sesión',
      code: '',
      isSession: true,
    })
  }
  return items
})

const visible = computed(() => {
  // Con `display-value`, el input arranca con la etiqueta de la opción
  // elegida ("frami · tu sesión"): eso no es algo que el usuario buscó, y
  // filtrar por ese texto dejaba la lista vacía al abrirla.
  if (!search.value.trim() || search.value === labelOf(comboValue.value)) return options.value
  const matching = new Set(filterDatabases(props.databases, search.value).map((d) => d.id))
  // La opción de la sesión se busca por el id real de su base; la genérica
  // (sin base conocida) no tiene nombre que buscar y se oculta al escribir.
  const idOf = (value: string) => (value === SESSION ? (props.sessionDatabaseId ?? '') : value)
  return options.value.filter((o) => matching.has(idOf(o.value)))
})

const comboValue = computed<string>({
  get: () => selected.value ?? SESSION,
  set: (value) => {
    selected.value = value === SESSION ? null : value
  },
})

function labelOf(value: string): string {
  const option = options.value.find((o) => o.value === value)
  if (!option) return ''
  return option.isSession && option.code ? `${option.label} · tu sesión` : option.label
}
</script>

<template>
  <div class="dbpicker">
    <label class="dbpicker__label" for="chat-database-picker">Cliente</label>
    <ComboboxRoot
      v-model="comboValue"
      :ignore-filter="true"
      :open-on-click="true"
      :reset-search-term-on-blur="true"
      :reset-search-term-on-select="true"
      class="dbpicker__root"
    >
      <ComboboxAnchor class="dbpicker__anchor">
        <ComboboxInput
          id="chat-database-picker"
          v-model="search"
          class="dbpicker__input"
          :display-value="labelOf"
          placeholder="Buscar cliente…"
          autocomplete="off"
          spellcheck="false"
          aria-label="Cliente"
        />
        <ComboboxTrigger class="dbpicker__trigger" aria-label="Ver clientes">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </ComboboxTrigger>
      </ComboboxAnchor>

      <ComboboxPortal>
        <ComboboxContent class="dbpicker__content" position="popper" side="top" :side-offset="6">
          <ComboboxViewport class="dbpicker__viewport">
            <ComboboxEmpty class="dbpicker__empty">Ningún cliente coincide.</ComboboxEmpty>
            <ComboboxItem
              v-for="option in visible"
              :key="option.value"
              :value="option.value"
              class="dbpicker__item"
            >
              <span class="dbpicker__item-name">{{ option.label }}</span>
              <span v-if="option.isSession && option.code" class="dbpicker__item-tag">tu sesión</span>
              <span v-else-if="option.code" class="dbpicker__item-code">{{ option.code }}</span>
            </ComboboxItem>
          </ComboboxViewport>
        </ComboboxContent>
      </ComboboxPortal>
    </ComboboxRoot>
    <span class="dbpicker__hint">Se fija al enviar el primer mensaje.</span>
  </div>
</template>

<style scoped>
.dbpicker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-2) var(--space-3);
  padding: 0 var(--space-5) var(--space-2);
  flex-shrink: 0;
}

.dbpicker__label {
  font-size: 11px;
  font-weight: var(--fw-medium);
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.dbpicker__root {
  max-width: 100%;
}

.dbpicker__anchor {
  display: flex;
  align-items: center;
  width: 280px;
  max-width: 100%;
  height: 32px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
}

.dbpicker__anchor:focus-within {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.dbpicker__input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0 var(--space-3);
  background: transparent;
  border: 0;
  outline: none;
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.dbpicker__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 100%;
  background: transparent;
  border: 0;
  color: var(--text-subtle);
  cursor: pointer;
}

.dbpicker__hint {
  font-size: 11px;
  color: var(--text-subtle);
}
</style>

<!-- El contenido se teletransporta al body: estos estilos no pueden ser scoped. -->
<style>
.dbpicker__content {
  z-index: 50;
  width: var(--reka-combobox-trigger-width);
  min-width: 240px;
  max-height: min(320px, var(--reka-combobox-content-available-height));
  overflow: hidden;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md, var(--r-sm));
  box-shadow: var(--shadow-md, 0 8px 24px rgba(0, 0, 0, 0.12));
}

/* Con muchos clientes la lista hace scroll en vez de salirse de la pantalla. */
.dbpicker__viewport {
  max-height: min(320px, var(--reka-combobox-content-available-height));
  overflow-y: auto;
  padding: var(--space-1, 4px);
}

.dbpicker__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}

.dbpicker__item[data-highlighted] {
  background: var(--surface-hover, rgba(0, 0, 0, 0.05));
  outline: none;
}

.dbpicker__item[data-state='checked'] .dbpicker__item-name {
  font-weight: var(--fw-semibold);
}

.dbpicker__item-code,
.dbpicker__item-tag {
  font-size: 11px;
  color: var(--text-subtle);
  white-space: nowrap;
}

.dbpicker__item-tag {
  color: var(--brand, var(--text-subtle));
}

.dbpicker__empty {
  padding: var(--space-3);
  font-size: 13px;
  color: var(--text-subtle);
  text-align: center;
}
</style>
