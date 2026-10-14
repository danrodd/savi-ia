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
  background: var(--ok-bg);
  color: var(--ok);
}
.tone-warn {
  background: var(--warn-bg);
  color: var(--warn);
}
.tone-bad {
  background: var(--bad-bg);
  color: var(--bad);
}
.tone-muted {
  background: var(--surface-2);
  color: var(--text-muted);
}
</style>
