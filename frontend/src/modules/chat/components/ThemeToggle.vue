<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from '@/composables/useTheme'

const { mode, cycleTheme } = useTheme()

const label = computed(() => {
  if (mode.value === 'light') return 'Tema: claro'
  if (mode.value === 'dark') return 'Tema: oscuro'
  return 'Tema: sistema'
})
</script>

<template>
  <button type="button" class="theme-toggle" :aria-label="label" :title="label" @click="cycleTheme">
    <svg
      v-if="mode === 'light'"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
    <svg
      v-else-if="mode === 'dark'"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
    <svg
      v-else
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <rect x="2" y="4" width="20" height="14" rx="2" />
      <path d="M8 22h8M12 18v4" />
    </svg>
    <span class="theme-toggle__label">{{ label }}</span>
  </button>
</template>

<style scoped>
.theme-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: var(--fw-medium);
  text-align: left;
  transition: background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.theme-toggle:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.theme-toggle svg {
  flex-shrink: 0;
}

.theme-toggle__label {
  letter-spacing: 0.01em;
}
</style>
