<script setup lang="ts">
import type { Tone } from '@/lib/format'

defineProps<{ tone: Tone; label: string }>()
</script>

<template>
  <span class="badge" :class="`tone-${tone}`">{{ label }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 0.1rem 0.55rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.tone-ok {
  background: var(--success-soft);
  color: var(--success);
}
.tone-warn {
  background: var(--warning-soft);
  color: var(--warning);
}
.tone-bad {
  background: var(--surface-danger);
  color: var(--danger);
}
.tone-muted {
  background: var(--surface-subtle);
  color: var(--text-muted);
}
</style>
