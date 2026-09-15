<script setup lang="ts">
import { computed } from 'vue'

import type { DocumentStatus } from '../types'
import { STATUS_LABELS } from '../utils/companyDocuments'

const props = defineProps<{
  status: DocumentStatus
  /** Mensaje del backend para `no_text`/`failed`: explica qué hacer. */
  message?: string | null
}>()

const info = computed(() => STATUS_LABELS[props.status])
</script>

<template>
  <span class="docstatus" :class="`docstatus--${info.tone}`" :title="message ?? undefined">
    <span class="docstatus__dot" aria-hidden="true" />
    {{ info.label }}
  </span>
</template>

<style scoped>
.docstatus {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: 11px;
  font-weight: var(--fw-medium);
  white-space: nowrap;
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.docstatus__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.docstatus--info {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.docstatus--info .docstatus__dot {
  animation: docstatus-pulse 1.2s ease-in-out infinite;
}

.docstatus--ok {
  background: var(--surface-success, rgba(22, 163, 74, 0.1));
  color: var(--text-success, #15803d);
}

.docstatus--warn {
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
}

.docstatus--danger {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}

@keyframes docstatus-pulse {
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .docstatus--info .docstatus__dot {
    animation: none;
  }
}
</style>
