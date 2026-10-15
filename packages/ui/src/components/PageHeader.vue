<script setup lang="ts">
/** Encabezado de una pantalla: título, descripción, datos breves y acciones. */
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <header class="ui-page-header">
    <div class="ui-page-header__main">
      <div v-if="$slots.eyebrow" class="ui-page-header__eyebrow"><slot name="eyebrow" /></div>
      <div class="ui-page-header__title-row">
        <h1 class="ui-page-header__title">{{ title }}</h1>
        <slot name="badges" />
      </div>
      <p v-if="description" class="ui-page-header__description">{{ description }}</p>
      <div v-if="$slots.meta" class="ui-page-header__meta"><slot name="meta" /></div>
    </div>
    <div v-if="$slots.actions" class="ui-page-header__actions"><slot name="actions" /></div>
  </header>
</template>

<style scoped>
.ui-page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.ui-page-header__main {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}

.ui-page-header__eyebrow {
  font-size: 12px;
  color: var(--text-muted);
}

.ui-page-header__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ui-page-header__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
  overflow-wrap: anywhere;
}

.ui-page-header__description {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted);
  max-width: 64ch;
}

.ui-page-header__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-4);
  font-size: 12px;
  color: var(--text-muted);
}

.ui-page-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
</style>
