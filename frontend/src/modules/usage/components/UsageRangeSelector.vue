<script setup lang="ts">
import { type RangeDays, useUsageStore } from '../stores/usageStore'

const store = useUsageStore()

const RANGES: { value: RangeDays; label: string }[] = [
  { value: 7, label: '7 días' },
  { value: 30, label: '30 días' },
  { value: 90, label: '90 días' },
]
</script>

<template>
  <div class="ranges" aria-label="Rango de tiempo">
    <button
      v-for="r in RANGES"
      :key="r.value"
      type="button"
      class="ranges__item"
      :class="{ 'ranges__item--active': store.rangeDays === r.value }"
      @click="store.setRange(r.value)"
    >
      {{ r.label }}
    </button>
  </div>
</template>

<style scoped>
.ranges {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.ranges__item {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.ranges__item:hover {
  color: var(--text);
}

.ranges__item--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}
</style>
