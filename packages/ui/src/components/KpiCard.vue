<script setup lang="ts">
import { CircleHelp } from 'lucide-vue-next'
import type { Component } from 'vue'
import type { Tone } from '../types'
import Tooltip from './Tooltip.vue'

/** Indicador: etiqueta, valor y una línea de contexto opcional. */
withDefaults(
  defineProps<{
    label: string
    value: string | number
    hint?: string
    tone?: Tone
    icon?: Component
    /** Definición de la métrica: se muestra al pasar o enfocar el ícono de ayuda. */
    help?: string
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <div class="ui-kpi" :class="`ui-kpi--${tone}`">
    <div class="ui-kpi__top">
      <span class="ui-kpi__label">
        {{ label }}
        <Tooltip v-if="help" :text="help">
          <button type="button" class="ui-kpi__help" :aria-label="`Qué es: ${help}`">
            <CircleHelp :size="13" aria-hidden="true" />
          </button>
        </Tooltip>
      </span>
      <span v-if="icon" class="ui-kpi__icon" aria-hidden="true"><component :is="icon" :size="16" /></span>
    </div>
    <strong class="ui-kpi__value">{{ value }}</strong>
    <!-- La línea de contexto siempre ocupa su lugar: así las tarjetas de una fila alinean. -->
    <span class="ui-kpi__hint"><slot name="hint">{{ hint }}</slot></span>
  </div>
</template>

<style scoped>
.ui-kpi {
  display: grid;
  grid-template-rows: auto auto 1fr;
  align-content: start;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-5);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-sm);
}

.ui-kpi__top {
  /* Alto fijo: el ícono de ayuda (24px) y el ícono de la tarjeta (30px) no deben mover el valor. */
  min-height: 30px;
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
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.ui-kpi__help {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  cursor: help;
}

.ui-kpi__help:hover,
.ui-kpi__help:focus-visible {
  color: var(--text);
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
  min-height: 1.4em;
  font-size: 12px;
  line-height: 1.4;
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
