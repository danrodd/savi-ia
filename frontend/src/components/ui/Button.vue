<script setup lang="ts">
import { computed } from 'vue'

/**
 * Botón base reutilizable con variantes y tamaños.
 *
 * Variantes: primary (crimson) · secondary (border) · ghost (transparente)
 *           · danger (igual a primary pero semánticamente destructivo)
 * Sizes: sm (28px) · md (36px) · lg (44px)
 *
 * Soporta estado loading (spinner + disabled) y modo icon-only (cuadrado).
 */

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    loading?: boolean
    disabled?: boolean
    icon?: boolean
    type?: 'button' | 'submit' | 'reset'
    fullWidth?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'md',
    type: 'button',
  },
)

const classes = computed(() => [
  'btn',
  `btn--${props.variant}`,
  `btn--${props.size}`,
  {
    'btn--loading': props.loading,
    'btn--icon': props.icon,
    'btn--full': props.fullWidth,
  },
])
</script>

<template>
  <button :class="classes" :disabled="disabled || loading" :type="type">
    <span v-if="loading" class="btn__spinner" aria-hidden="true" />
    <span class="btn__content" :class="{ 'btn__content--hidden': loading }">
      <slot />
    </span>
  </button>
</template>

<style scoped>
.btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-radius: var(--r-md);
  border: 1px solid transparent;
  font-family: var(--font-sans);
  font-weight: var(--fw-medium);
  letter-spacing: 0.005em;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
  user-select: none;
  white-space: nowrap;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.btn:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.btn--full {
  width: 100%;
}

/* Sizes */
.btn--sm {
  height: 28px;
  padding: 0 var(--space-3);
  font-size: 12px;
}
.btn--md {
  height: 36px;
  padding: 0 var(--space-5);
  font-size: 13px;
}
.btn--lg {
  height: 44px;
  padding: 0 var(--space-6);
  font-size: 14px;
}

.btn--icon.btn--sm {
  width: 28px;
  padding: 0;
}
.btn--icon.btn--md {
  width: 36px;
  padding: 0;
}
.btn--icon.btn--lg {
  width: 44px;
  padding: 0;
}

/* Variants */
.btn--primary,
.btn--danger {
  background: var(--brand);
  color: var(--text-on-brand);
  box-shadow: var(--shadow-inset);
}

.btn--primary:hover:not(:disabled),
.btn--danger:hover:not(:disabled) {
  background: var(--brand-strong);
  transform: translateY(-0.5px);
}

.btn--secondary {
  background: var(--surface-elev);
  border-color: var(--border);
  color: var(--text);
}

.btn--secondary:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: var(--border-strong);
}

.btn--ghost {
  background: transparent;
  color: var(--text-muted);
}

.btn--ghost:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text);
}

/* Loading */
.btn__content {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  transition: opacity var(--duration-fast) var(--ease-out);
}

.btn__content--hidden {
  opacity: 0;
}

.btn__spinner {
  position: absolute;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: btn-spin 0.7s linear infinite;
}

@keyframes btn-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
