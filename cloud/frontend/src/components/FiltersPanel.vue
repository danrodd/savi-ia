<script setup lang="ts">
import { Card } from '@savi/ui'
import { ChevronDown, SlidersHorizontal } from 'lucide-vue-next'
import { ref, useId } from 'vue'

/**
 * Tarjeta de filtros de una lista. En pantallas anchas se ve completa; en el celular queda
 * detrás de un botón "Filtros", así el primer resultado aparece en la primera pantalla.
 */
defineProps<{
  /** Cuántos filtros tienen un valor distinto del predeterminado. */
  active?: number
}>()

const open = ref(false)
const id = `filters-${useId()}`
</script>

<template>
  <Card padding="md" class="filters-panel" :class="{ 'filters-panel--open': open }">
    <button
      type="button"
      class="filters-panel__toggle"
      :aria-expanded="open"
      :aria-controls="id"
      data-test="filters-toggle"
      @click="open = !open"
    >
      <SlidersHorizontal :size="15" aria-hidden="true" />
      Filtros
      <span v-if="active" class="filters-panel__count">{{ active }}</span>
      <ChevronDown :size="15" class="filters-panel__chevron" aria-hidden="true" />
    </button>
    <div :id="id" class="filters-panel__body">
      <slot />
    </div>
  </Card>
</template>

<style scoped>
.filters-panel__toggle {
  display: none;
}

@media (max-width: 720px) {
  .filters-panel__toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: 36px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 14px;
    font-weight: var(--fw-medium);
    cursor: pointer;
  }

  .filters-panel__count {
    display: inline-grid;
    place-items: center;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 999px;
    background: var(--surface-subtle);
    font-size: 12px;
  }

  .filters-panel__chevron {
    margin-left: auto;
    color: var(--text-muted);
    transition: transform 150ms ease;
  }

  .filters-panel--open .filters-panel__chevron {
    transform: rotate(180deg);
  }

  .filters-panel__body {
    display: none;
  }

  .filters-panel--open .filters-panel__body {
    display: block;
    margin-top: var(--space-4);
  }
}
</style>
