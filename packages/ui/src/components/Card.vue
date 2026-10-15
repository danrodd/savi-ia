<script setup lang="ts">
/** Contenedor con el borde, radio y sombra de las tarjetas de SAVI. */
withDefaults(
  defineProps<{
    title?: string
    description?: string
    /** `none` para tablas o listas que llegan hasta el borde. */
    padding?: 'none' | 'md' | 'lg'
    as?: 'section' | 'div' | 'article'
  }>(),
  { padding: 'lg', as: 'section' },
)
</script>

<template>
  <component :is="as" class="ui-card" :class="`ui-card--pad-${padding}`">
    <header v-if="title || $slots.header || $slots.actions" class="ui-card__header">
      <slot name="header">
        <div class="ui-card__heading">
          <h2 v-if="title" class="ui-card__title">{{ title }}</h2>
          <p v-if="description" class="ui-card__description">{{ description }}</p>
        </div>
      </slot>
      <div v-if="$slots.actions" class="ui-card__actions"><slot name="actions" /></div>
    </header>
    <div class="ui-card__body"><slot /></div>
    <footer v-if="$slots.footer" class="ui-card__footer"><slot name="footer" /></footer>
  </component>
</template>

<style scoped>
.ui-card {
  min-width: 0;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-sm);
}

.ui-card--pad-lg {
  --ui-card-pad: var(--space-6);
}

.ui-card--pad-md {
  --ui-card-pad: var(--space-5);
}

.ui-card--pad-none {
  --ui-card-pad: 0;
  overflow: hidden;
}

.ui-card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3) var(--space-4);
  padding: var(--space-6) var(--space-6) 0;
}

.ui-card--pad-md .ui-card__header {
  padding: var(--space-5) var(--space-5) 0;
}

.ui-card--pad-none .ui-card__header {
  padding-bottom: var(--space-5);
  border-bottom: 1px solid var(--border);
}

.ui-card__heading {
  display: grid;
  gap: var(--space-1);
  min-width: 0;
}

.ui-card__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.ui-card__description {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted);
  max-width: 70ch;
}

.ui-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.ui-card__body {
  padding: var(--ui-card-pad);
}

.ui-card__header + .ui-card__body {
  padding-top: var(--space-5);
}

.ui-card--pad-none .ui-card__header + .ui-card__body {
  padding-top: 0;
}

.ui-card__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border);
  background: var(--surface);
  border-radius: 0 0 var(--r-lg) var(--r-lg);
}
</style>
