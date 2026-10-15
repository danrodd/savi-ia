<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useClientContext } from '@/lib/clientContext'
import { OPERATION_SECTIONS, type OperationSection } from '@/lib/clientRoutes'

/**
 * Operación: lo que reportan las instalaciones del cliente. Instancias, sucursales y personas
 * son subsecciones con URL propia (`/operacion/<sección>`) bajo un selector segmentado.
 */
const { id, client, counts } = useClientContext()

const LABELS: Record<OperationSection, string> = {
  instancias: 'Instancias',
  sucursales: 'Sucursales',
  personas: 'Personas',
}

const items = computed(() =>
  OPERATION_SECTIONS.map((key) => ({
    key,
    label: LABELS[key],
    to: `/clientes/${id.value}/operacion/${key}`,
    count:
      key === 'instancias'
        ? client.value?.instances_total
        : key === 'personas'
          ? counts.value?.people
          : undefined,
  })),
)
</script>

<template>
  <div class="operation">
    <nav class="segments" aria-label="Operación del cliente">
      <RouterLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        class="segments__item"
        active-class="segments__item--active"
        :data-test="`operation-${item.key}`"
      >
        {{ item.label }}
        <span v-if="item.count !== undefined" class="segments__count">{{ item.count }}</span>
      </RouterLink>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.operation {
  display: grid;
  gap: var(--space-5);
  min-width: 0;
}

.segments {
  display: inline-flex;
  max-width: 100%;
  justify-self: start;
  gap: 2px;
  padding: 3px;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
  scrollbar-width: none;
}

.segments::-webkit-scrollbar {
  display: none;
}

.segments__item {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  gap: var(--space-2);
  min-height: 32px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  text-decoration: none;
  white-space: nowrap;
}

.segments__item:hover {
  color: var(--text);
}

.segments__item--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-sm);
}

.segments__count {
  padding: 0 7px;
  border-radius: var(--r-pill);
  background: var(--surface-subtle);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: var(--fw-semibold);
}

.segments__item--active .segments__count {
  background: var(--surface-subtle);
}
</style>
