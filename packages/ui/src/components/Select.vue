<script setup lang="ts" generic="T extends string | number">
import '../styles/field.css'
import type { SelectOption } from '../types'
import FormField from './FormField.vue'

/**
 * Lista desplegable nativa con el estilo de SAVI. Nativa a propósito: teclado,
 * lectores de pantalla y móviles funcionan sin trabajo extra.
 */
const props = defineProps<{
  options: SelectOption<T>[]
  label?: string
  hint?: string
  error?: string | null
  /** Texto de la opción vacía; sin él no hay opción vacía. */
  placeholder?: string
  required?: boolean
  disabled?: boolean
  id?: string
  /** Nombre accesible cuando no hay etiqueta visible (por ejemplo, dentro de una tabla). */
  ariaLabel?: string
}>()

const model = defineModel<T | null>({ default: null })
const emit = defineEmits<{ blur: [] }>()

function onChange(event: Event): void {
  const index = (event.target as HTMLSelectElement).selectedIndex - (props.placeholder ? 1 : 0)
  model.value = index < 0 ? null : (props.options[index]?.value ?? null)
}
</script>

<template>
  <FormField v-slot="field" :label="label" :hint="hint" :error="error" :required="required" :id="id">
    <div class="ui-select">
      <select
        v-bind="field"
        class="ui-input ui-select__control"
        :aria-label="ariaLabel"
        :required="required"
        :disabled="disabled"
        @change="onChange"
        @blur="emit('blur')"
      >
        <option v-if="placeholder" value="" :selected="model === null">{{ placeholder }}</option>
        <option
          v-for="option in options"
          :key="String(option.value)"
          :value="String(option.value)"
          :disabled="option.disabled"
          :selected="option.value === model"
        >
          {{ option.label }}
        </option>
      </select>
      <svg class="ui-select__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  </FormField>
</template>

<style scoped>
.ui-select {
  position: relative;
}

.ui-select__control {
  appearance: none;
  padding-right: calc(var(--space-3) + 20px);
  cursor: pointer;
}

.ui-select__chevron {
  position: absolute;
  top: 50%;
  right: var(--space-3);
  transform: translateY(-50%);
  color: var(--text-subtle);
  pointer-events: none;
}
</style>
