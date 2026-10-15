<script setup lang="ts">
import { Check, Eye, EyeOff } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import '../styles/field.css'
import type { PasswordRule } from '../types'
import FormField from './FormField.vue'

/**
 * Contraseña con botón mostrar/ocultar y, si recibe `rules`, la lista de
 * requisitos tildándose mientras se escribe. Las reglas las define la app: el
 * paquete no conoce la política de ninguna.
 */
const props = withDefaults(
  defineProps<{
    label?: string
    hint?: string
    error?: string | null
    rules?: PasswordRule[]
    required?: boolean
    disabled?: boolean
    autocomplete?: 'current-password' | 'new-password' | 'off'
    id?: string
  }>(),
  { rules: () => [], autocomplete: 'current-password' },
)

const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ blur: [] }>()
const visible = ref(false)

const checks = computed(() =>
  props.rules.map((rule) => ({ label: rule.label, ok: rule.test(model.value) })),
)
</script>

<template>
  <FormField v-slot="field" :label="label" :hint="hint" :error="error" :required="required" :id="id">
    <div class="ui-password">
      <input
        v-bind="field"
        v-model="model"
        class="ui-input ui-password__input"
        :type="visible ? 'text' : 'password'"
        :required="required"
        :disabled="disabled"
        :autocomplete="autocomplete"
        spellcheck="false"
        @blur="emit('blur')"
      />
      <button
        type="button"
        class="ui-password__toggle"
        :aria-label="visible ? 'Ocultar contraseña' : 'Mostrar contraseña'"
        :aria-pressed="visible"
        :disabled="disabled"
        @click="visible = !visible"
      >
        <EyeOff v-if="visible" :size="16" aria-hidden="true" />
        <Eye v-else :size="16" aria-hidden="true" />
      </button>
    </div>
    <ul v-if="checks.length" class="ui-password__rules" aria-label="Requisitos de la contraseña">
      <li
        v-for="check in checks"
        :key="check.label"
        class="ui-password__rule"
        :class="{ 'ui-password__rule--ok': check.ok }"
      >
        <span class="ui-password__mark" aria-hidden="true">
          <Check v-if="check.ok" :size="12" :stroke-width="3" />
        </span>
        {{ check.label }}
        <span class="ui-sr-only">{{ check.ok ? '(cumplido)' : '(pendiente)' }}</span>
      </li>
    </ul>
  </FormField>
</template>

<style scoped>
.ui-password {
  position: relative;
}

.ui-password__input {
  padding-right: 44px;
}

.ui-password__toggle {
  position: absolute;
  top: 50%;
  right: 2px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  transform: translateY(-50%);
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.ui-password__toggle:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text);
}

.ui-password__toggle:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.ui-password__rules {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0 0;
  padding: 0;
  list-style: none;
}

.ui-password__rule {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
  color: var(--text-muted);
  transition: color var(--duration-fast) var(--ease-out);
}

.ui-password__rule--ok {
  color: var(--success);
}

.ui-password__mark {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--border-strong);
  border-radius: 50%;
}

.ui-password__rule--ok .ui-password__mark {
  border-color: var(--success);
  background: var(--success);
  color: var(--surface-elev);
}

.ui-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
