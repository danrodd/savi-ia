<script setup lang="ts">
import { computed, useId } from 'vue'

/**
 * Etiqueta, ayuda y error de un control. Cablea `id`, `aria-describedby` y
 * `aria-invalid` y se los pasa al control por el slot, así cada campo queda
 * accesible sin repetir el armado.
 *
 * Uso:
 *   <FormField label="Nombre" :error="errors.name" v-slot="field">
 *     <input v-bind="field" v-model="name" />
 *   </FormField>
 */
const props = defineProps<{
  label?: string
  hint?: string
  error?: string | null
  required?: boolean
  /** Fija el id del control (por defecto se genera uno). */
  id?: string
}>()

const generated = useId()
const controlId = computed(() => props.id ?? `field-${generated}`)
const hintId = computed(() => `${controlId.value}-hint`)
const errorId = computed(() => `${controlId.value}-error`)

const describedBy = computed(() => {
  const ids = [props.hint ? hintId.value : null, props.error ? errorId.value : null]
  return ids.filter(Boolean).join(' ') || undefined
})

const controlAttrs = computed(() => ({
  id: controlId.value,
  'aria-describedby': describedBy.value,
  'aria-invalid': props.error ? ('true' as const) : undefined,
  'aria-required': props.required ? ('true' as const) : undefined,
}))
</script>

<template>
  <div class="ui-field" :class="{ 'ui-field--invalid': !!error }">
    <label v-if="label" class="ui-field__label" :for="controlId">
      {{ label }}<span v-if="required" class="ui-field__required" aria-hidden="true"> *</span>
    </label>
    <slot v-bind="controlAttrs" />
    <p v-if="hint" :id="hintId" class="ui-field__hint">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="ui-field__error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.ui-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.ui-field__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.ui-field--invalid .ui-field__label {
  color: var(--text-danger);
}

.ui-field__required {
  color: var(--brand);
}

.ui-field__hint,
.ui-field__error {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.4;
}

.ui-field__hint {
  color: var(--text-subtle);
}

.ui-field__error {
  color: var(--text-danger);
  font-weight: var(--fw-medium);
}
</style>
