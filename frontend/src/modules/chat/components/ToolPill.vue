<script setup lang="ts">
import type { ToolCallGroup } from '../types'

defineProps<{ group: ToolCallGroup }>()
</script>

<template>
  <div class="pill" :class="`pill--${group.status}`">
    <span class="pill__dot">
      <svg v-if="group.status === 'running'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="7" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <svg v-else-if="group.status === 'success'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 9v4M12 17h.01" />
        <circle cx="12" cy="12" r="9" />
      </svg>
    </span>
    <span class="pill__label">{{ group.label }}</span>
    <span v-if="group.count > 1" class="pill__count">×{{ group.count }}</span>
  </div>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4) var(--space-2) var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text-muted);
  transition: all var(--duration-normal) var(--ease-out);
}

.pill__dot {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--success-soft);
  color: var(--success);
  flex-shrink: 0;
}

.pill--running .pill__dot {
  background: var(--brand-soft);
  color: var(--brand);
}

.pill--running .pill__dot::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1.5px solid var(--brand);
  opacity: 0.6;
  animation: pill-pulse 1.2s ease-out infinite;
}

.pill--error {
  border-color: var(--brand);
  color: var(--brand);
}

.pill--error .pill__dot {
  background: var(--brand-soft);
  color: var(--brand);
}

.pill__count {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-subtle);
  letter-spacing: 0.02em;
}

.pill--error .pill__count {
  color: var(--brand);
}

@keyframes pill-pulse {
  0% {
    opacity: 0.6;
    transform: scale(1);
  }
  100% {
    opacity: 0;
    transform: scale(1.6);
  }
}
</style>
