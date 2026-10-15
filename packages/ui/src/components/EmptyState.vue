<script setup lang="ts">
import type { Component } from 'vue'

/** Estado vacío: qué falta y, si corresponde, la acción para resolverlo. */
defineProps<{
  title: string
  description?: string
  icon?: Component
}>()
</script>

<template>
  <div class="ui-empty">
    <span v-if="icon" class="ui-empty__icon" aria-hidden="true">
      <component :is="icon" :size="20" />
    </span>
    <p class="ui-empty__title">{{ title }}</p>
    <p v-if="description" class="ui-empty__description">{{ description }}</p>
    <div v-if="$slots.default" class="ui-empty__actions"><slot /></div>
  </div>
</template>

<style scoped>
.ui-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-6);
  text-align: center;
}

.ui-empty__icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  margin-bottom: var(--space-2);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.ui-empty__title {
  margin: 0;
  font-size: 14px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.ui-empty__description {
  margin: 0;
  max-width: 46ch;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted);
}

.ui-empty__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
</style>
