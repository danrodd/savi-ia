<script setup lang="ts">
import { Check } from 'lucide-vue-next'
import { computed } from 'vue'
import type { StepItem } from '../types'

/** Progreso de un flujo por pasos. Solo muestra; los pasos los avanza la app. */
const props = defineProps<{
  steps: StepItem[]
  current: string
}>()

const currentIndex = computed(() => props.steps.findIndex((step) => step.key === props.current))
</script>

<template>
  <ol class="ui-stepper" aria-label="Progreso">
    <li
      v-for="(step, index) in steps"
      :key="step.key"
      class="ui-stepper__step"
      :class="{
        'ui-stepper__step--done': index < currentIndex,
        'ui-stepper__step--current': index === currentIndex,
      }"
      :aria-current="index === currentIndex ? 'step' : undefined"
    >
      <span class="ui-stepper__marker" aria-hidden="true">
        <Check v-if="index < currentIndex" :size="12" :stroke-width="3" />
        <template v-else>{{ index + 1 }}</template>
      </span>
      <span class="ui-stepper__label">{{ step.label }}</span>
    </li>
  </ol>
</template>

<style scoped>
.ui-stepper {
  display: flex;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ui-stepper__step {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  min-width: 0;
  color: var(--text-subtle);
  font-size: 12px;
  font-weight: var(--fw-medium);
}

.ui-stepper__step + .ui-stepper__step::before {
  content: '';
  flex: 0 0 12px;
  height: 1px;
  margin-right: var(--space-1);
  background: var(--border-strong);
}

.ui-stepper__marker {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: 1.5px solid var(--border-strong);
  border-radius: 50%;
  font-size: 11px;
}

.ui-stepper__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-stepper__step--current {
  color: var(--text);
}

.ui-stepper__step--current .ui-stepper__marker {
  border-color: var(--brand);
  background: var(--brand);
  color: var(--text-on-brand);
}

.ui-stepper__step--done {
  color: var(--text-muted);
}

.ui-stepper__step--done .ui-stepper__marker {
  border-color: var(--success);
  background: var(--success);
  color: var(--surface-elev);
}

@media (max-width: 480px) {
  .ui-stepper__step:not(.ui-stepper__step--current) .ui-stepper__label {
    display: none;
  }
}
</style>
