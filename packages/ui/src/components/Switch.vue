<script setup lang="ts">
import { useId } from 'vue'

/** Interruptor encendido/apagado (`role="switch"`). Para opciones que aplican al instante. */
defineProps<{
  label: string
  description?: string
  disabled?: boolean
}>()

const model = defineModel<boolean>({ default: false })
const id = `switch-${useId()}`
</script>

<template>
  <div class="ui-switch" :class="{ 'ui-switch--disabled': disabled }">
    <span class="ui-switch__text">
      <span :id="`${id}-label`" class="ui-switch__label">{{ label }}</span>
      <span v-if="description" :id="`${id}-desc`" class="ui-switch__description">{{ description }}</span>
    </span>
    <button
      type="button"
      role="switch"
      class="ui-switch__track"
      :class="{ 'ui-switch__track--on': model }"
      :aria-checked="model"
      :aria-labelledby="`${id}-label`"
      :aria-describedby="description ? `${id}-desc` : undefined"
      :disabled="disabled"
      @click="model = !model"
    >
      <span class="ui-switch__thumb" aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.ui-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
}

.ui-switch--disabled {
  opacity: 0.6;
}

.ui-switch__text {
  display: grid;
  gap: 2px;
}

.ui-switch__label {
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
}

.ui-switch__description {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

.ui-switch__track {
  position: relative;
  flex-shrink: 0;
  width: 38px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--border-strong);
  border-radius: var(--r-pill);
  background: var(--surface-subtle);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
}

.ui-switch__track:disabled {
  cursor: not-allowed;
}

.ui-switch__track:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.ui-switch__track--on {
  background: var(--brand);
  border-color: var(--brand);
}

.ui-switch__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--surface-elev);
  box-shadow: var(--shadow-sm);
  transition: transform var(--duration-fast) var(--ease-out);
}

.ui-switch__track--on .ui-switch__thumb {
  transform: translateX(16px);
}
</style>
