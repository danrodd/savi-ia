<script setup lang="ts">
import type { Tone } from '../types'

/** Etiqueta de estado corta ("Activo", "Vencida", "3"). */
withDefaults(
  defineProps<{
    tone?: Tone
    /** Punto de color antes del texto. */
    dot?: boolean
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span class="ui-badge" :class="`ui-badge--${tone}`">
    <span v-if="dot" class="ui-badge__dot" aria-hidden="true" />
    <slot />
  </span>
</template>

<style scoped>
.ui-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
  padding: 2px 9px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: var(--fw-semibold);
  line-height: 1.5;
  white-space: nowrap;
}

.ui-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.ui-badge--neutral {
  color: var(--text-muted);
  background: var(--surface-subtle);
}

.ui-badge--success {
  color: var(--success);
  background: var(--success-soft);
}

.ui-badge--warning {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 14%, transparent);
}

.ui-badge--danger {
  color: var(--danger);
  background: var(--surface-danger);
}

.ui-badge--info {
  /* El azul solo no llega a 4.5:1 sobre su fondo en oscuro: se mezcla con el texto del tema. */
  color: color-mix(in srgb, var(--navy) 70%, var(--text));
  background: var(--navy-soft);
}

.ui-badge--brand {
  color: var(--brand-strong);
  background: var(--brand-soft);
}
</style>
