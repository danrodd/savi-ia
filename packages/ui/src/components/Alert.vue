<script setup lang="ts">
import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-vue-next'
import { computed } from 'vue'
import type { Tone } from '../types'

/**
 * Aviso dentro de la página (no flotante). Los de peligro se anuncian como
 * `alert`; los demás como `status`, sin interrumpir al lector de pantalla.
 */
const props = withDefaults(
  defineProps<{
    tone?: Exclude<Tone, 'neutral' | 'brand'>
    title?: string
  }>(),
  { tone: 'info' },
)

const icon = computed(
  () =>
    ({ success: CircleCheck, warning: TriangleAlert, danger: CircleAlert, info: Info })[props.tone],
)
</script>

<template>
  <div class="ui-alert" :class="`ui-alert--${tone}`" :role="tone === 'danger' ? 'alert' : 'status'">
    <component :is="icon" class="ui-alert__icon" :size="16" aria-hidden="true" />
    <div class="ui-alert__body">
      <strong v-if="title" class="ui-alert__title">{{ title }}</strong>
      <div class="ui-alert__text"><slot /></div>
    </div>
    <div v-if="$slots.action" class="ui-alert__action"><slot name="action" /></div>
  </div>
</template>

<style scoped>
.ui-alert {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid transparent;
  border-radius: var(--r-md);
  font-size: 12.5px;
  line-height: 1.5;
}

.ui-alert__icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.ui-alert__body {
  display: grid;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.ui-alert__title {
  font-weight: var(--fw-semibold);
}

.ui-alert__text {
  color: var(--text);
}

.ui-alert__action {
  flex-shrink: 0;
  align-self: center;
}

.ui-alert--info {
  color: var(--navy);
  background: var(--navy-soft);
  border-color: color-mix(in srgb, var(--navy) 22%, transparent);
}

.ui-alert--success {
  color: var(--success);
  background: var(--success-soft);
  border-color: color-mix(in srgb, var(--success) 25%, transparent);
}

.ui-alert--warning {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 10%, transparent);
  border-color: color-mix(in srgb, var(--warning) 28%, transparent);
}

.ui-alert--danger {
  color: var(--danger);
  background: var(--surface-danger);
  border-color: color-mix(in srgb, var(--danger) 25%, transparent);
}
</style>
