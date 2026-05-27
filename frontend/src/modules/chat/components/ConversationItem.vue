<script setup lang="ts">
import { computed } from 'vue'
import type { Conversation } from '../types'

const props = defineProps<{ conversation: Conversation; active: boolean }>()

const time = computed(() => {
  const d = new Date(props.conversation.updated_at)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'ahora'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'ayer'
  if (days < 7) return `${days}d`
  return d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })
})
</script>

<template>
  <button type="button" class="item" :class="{ 'item--active': active }">
    <span class="item__title">{{ conversation.title }}</span>
    <span class="item__time">{{ time }}</span>
  </button>
</template>

<style scoped>
.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 13px;
  font-weight: var(--fw-regular);
  transition: background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out);
}

.item:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.item--active {
  background: var(--surface-elev);
  border-color: var(--border);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.item__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  font-weight: var(--fw-medium);
  letter-spacing: -0.005em;
}

.item__time {
  flex-shrink: 0;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-subtle);
  letter-spacing: 0.02em;
}
</style>
