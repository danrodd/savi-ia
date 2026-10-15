<script setup lang="ts">
import '../styles/field.css'
import FormField from './FormField.vue'

withDefaults(
  defineProps<{
    label?: string
    hint?: string
    error?: string | null
    placeholder?: string
    required?: boolean
    disabled?: boolean
    rows?: number
    maxlength?: number
    id?: string
  }>(),
  { rows: 3 },
)

const model = defineModel<string | null>({ default: '' })
const emit = defineEmits<{ blur: [] }>()
</script>

<template>
  <FormField v-slot="field" :label="label" :hint="hint" :error="error" :required="required" :id="id">
    <textarea
      v-bind="field"
      class="ui-input"
      :value="model ?? ''"
      :rows="rows"
      :placeholder="placeholder"
      :required="required"
      :disabled="disabled"
      :maxlength="maxlength"
      @input="model = ($event.target as HTMLTextAreaElement).value"
      @blur="emit('blur')"
    />
  </FormField>
</template>
