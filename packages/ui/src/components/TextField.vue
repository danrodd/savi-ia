<script setup lang="ts">
import '../styles/field.css'
import FormField from './FormField.vue'

/**
 * Campo de texto de una línea con etiqueta, ayuda y error. Con `type="number"`
 * el modelo es un número (o `null` si queda vacío).
 */
withDefaults(
  defineProps<{
    label?: string
    hint?: string
    error?: string | null
    type?: 'text' | 'email' | 'number' | 'url' | 'search' | 'tel' | 'date'
    placeholder?: string
    required?: boolean
    disabled?: boolean
    readonly?: boolean
    mono?: boolean
    autocomplete?: string
    maxlength?: number
    min?: number | string
    max?: number | string
    step?: number | string
    inputmode?: 'text' | 'numeric' | 'decimal' | 'email' | 'url' | 'search' | 'tel'
    id?: string
    /** Nombre accesible cuando no hay etiqueta visible (por ejemplo, dentro de una tabla). */
    ariaLabel?: string
  }>(),
  { type: 'text' },
)

const model = defineModel<string | number | null>({ default: '' })
const emit = defineEmits<{ blur: [] }>()

function onInput(event: Event, type: string): void {
  const raw = (event.target as HTMLInputElement).value
  if (type !== 'number') {
    model.value = raw
    return
  }
  model.value = raw === '' ? null : Number(raw)
}
</script>

<template>
  <FormField v-slot="field" :label="label" :hint="hint" :error="error" :required="required" :id="id">
    <div class="ui-text">
      <span v-if="$slots.prefix" class="ui-text__affix ui-text__affix--prefix"><slot name="prefix" /></span>
      <input
        v-bind="field"
        class="ui-input"
        :aria-label="ariaLabel"
        :class="{ 'ui-input--mono': mono, 'ui-text__input--prefixed': $slots.prefix, 'ui-text__input--suffixed': $slots.suffix }"
        :type="type"
        :value="model ?? ''"
        :placeholder="placeholder"
        :required="required"
        :disabled="disabled"
        :readonly="readonly"
        :autocomplete="autocomplete"
        :maxlength="maxlength"
        :min="min"
        :max="max"
        :step="step"
        :inputmode="inputmode"
        @input="onInput($event, type)"
        @blur="emit('blur')"
      />
      <span v-if="$slots.suffix" class="ui-text__affix ui-text__affix--suffix"><slot name="suffix" /></span>
    </div>
  </FormField>
</template>

<style scoped>
.ui-text {
  position: relative;
  display: flex;
  align-items: center;
}

.ui-text__affix {
  position: absolute;
  display: inline-flex;
  align-items: center;
  color: var(--text-subtle);
  font-size: 12px;
  pointer-events: none;
}

.ui-text__affix--prefix {
  left: var(--space-3);
}

.ui-text__affix--suffix {
  right: var(--space-3);
}

.ui-text__input--prefixed {
  padding-left: calc(var(--space-3) + 26px);
}

.ui-text__input--suffixed {
  padding-right: calc(var(--space-3) + 40px);
}
</style>
