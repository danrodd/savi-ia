<script setup lang="ts">
import type { Component } from 'vue'
import type { Tone } from '../types'

/** Indicador: etiqueta, valor y una línea de contexto opcional. */
withDefaults(
  defineProps<{
    label: string
    value: string | number
    hint?: string
    tone?: Tone
    icon?: Component
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <div class="ui-kpi" :class="`ui-kpi--${tone}`">
    <div class="ui-kpi__top">
      <span class="ui-kpi__label">{{ label }}</span>
      <span v-if="icon" class="ui-kpi__icon" aria-hidden="true"><component :is="icon" :size="16" /></span>
    </div>
    <strong class="ui-kpi__value">{{ value }}</strong>
    <span v-if="hint || $slots.hint" class="ui-kpi__hint"><slot name="hint">{{ hint }}</slot></span>
  </div>
</template>

<style scoped>
.ui-kpi {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-5);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-sm);
}

.ui-kpi__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.ui-kpi__label {
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
}

.ui-kpi__icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--r-sm);
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.ui-kpi__value {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: var(--fw-semibold);
  line-height: 1.15;
  color: var(--text);
  overflow-wrap: anywhere;
}

.ui-kpi__hint {
  font-size: 12px;
  color: var(--text-muted);
}

.ui-kpi--success .ui-kpi__icon {
  color: var(--success);
  background: var(--success-soft);
}

.ui-kpi--warning .ui-kpi__icon {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 14%, transparent);
}

.ui-kpi--danger .ui-kpi__icon {
  color: var(--danger);
  background: var(--surface-danger);
}

.ui-kpi--danger .ui-kpi__value {
  color: var(--danger);
}

.ui-kpi--info .ui-kpi__icon {
  color: var(--navy);
  background: var(--navy-soft);
}

.ui-kpi--brand .ui-kpi__icon {
  color: var(--brand);
  background: var(--brand-soft);
}
</style>
