<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  current: number
  total: number
  loading?: boolean
}>()
const emit = defineEmits<{ prev: []; next: []; load: [] }>()

const canPrev = computed(() => props.current > 1)
const canNext = computed(() => props.current < props.total)
</script>

<template>
  <div class="nav">
    <button
      type="button"
      class="nav__btn"
      :disabled="!canPrev || loading"
      aria-label="Versión anterior"
      @click="emit('prev')"
    >
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="m15 18-6-6 6-6" />
      </svg>
    </button>
    <span v-if="loading" class="nav__label">…</span>
    <span v-else class="nav__label">{{ current }} / {{ total }}</span>
    <button
      type="button"
      class="nav__btn"
      :disabled="!canNext || loading"
      aria-label="Versión siguiente"
      @click="emit('next')"
    >
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="m9 18 6-6-6-6" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.nav {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-muted);
  user-select: none;
}

.nav__btn {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.nav__btn:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text);
}

.nav__btn:disabled {
  cursor: default;
  opacity: 0.35;
}

.nav__label {
  padding: 0 var(--space-2);
  letter-spacing: 0.02em;
}
</style>
