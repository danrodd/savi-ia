<script setup lang="ts">
import { nextTick, onMounted, onUpdated, ref } from 'vue'
import { RouterLink } from 'vue-router'
import type { TabItem } from '../types'

/**
 * Pestañas. Si cada ítem trae `to`, son enlaces del router (la URL recuerda la
 * pestaña y se puede compartir) y la activa la marca el router. Si no, son
 * pestañas locales controladas con `v-model` y se recorren con las flechas.
 */
const props = defineProps<{
  items: TabItem[]
  label: string
}>()

const model = defineModel<string>()
const root = ref<HTMLElement | null>(null)

/** En pantallas chicas la barra se desplaza: la pestaña activa siempre queda a la vista. */
function revealActive(): void {
  void nextTick(() => {
    const active = root.value?.querySelector<HTMLElement>('.ui-tabs__tab--active')
    active?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  })
}

onMounted(revealActive)
onUpdated(revealActive)

function onKeydown(event: KeyboardEvent, index: number): void {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
  event.preventDefault()
  const step = event.key === 'ArrowRight' ? 1 : -1
  const next = (index + step + props.items.length) % props.items.length
  const item = props.items[next]
  if (!item) return
  model.value = item.key
  const list = (event.currentTarget as HTMLElement).parentElement
  ;(list?.children[next] as HTMLElement | undefined)?.focus()
}
</script>

<template>
  <nav v-if="items.some((item) => item.to)" ref="root" class="ui-tabs" :aria-label="label">
    <RouterLink
      v-for="item in items"
      :key="item.key"
      :to="item.to ?? ''"
      class="ui-tabs__tab"
      active-class="ui-tabs__tab--active"
      exact-active-class="ui-tabs__tab--active"
    >
      {{ item.label }}
      <span v-if="item.count !== undefined" class="ui-tabs__count">{{ item.count }}</span>
    </RouterLink>
  </nav>
  <div v-else ref="root" class="ui-tabs" role="tablist" :aria-label="label">
    <button
      v-for="(item, index) in items"
      :key="item.key"
      type="button"
      role="tab"
      class="ui-tabs__tab"
      :class="{ 'ui-tabs__tab--active': model === item.key }"
      :aria-selected="model === item.key"
      :tabindex="model === item.key ? 0 : -1"
      @click="model = item.key"
      @keydown="onKeydown($event, index)"
    >
      {{ item.label }}
      <span v-if="item.count !== undefined" class="ui-tabs__count">{{ item.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.ui-tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-6);
  overflow-x: auto;
  border-bottom: 1px solid var(--border);
  scrollbar-width: none;
}

.ui-tabs::-webkit-scrollbar {
  display: none;
}

.ui-tabs__tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
  min-height: 40px;
  padding: 0 var(--space-4);
  border: none;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 13px;
  font-weight: var(--fw-medium);
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-out);
}

.ui-tabs__tab:hover {
  color: var(--text);
}

.ui-tabs__tab:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: -2px;
  border-radius: var(--r-sm);
}

.ui-tabs__tab::after {
  content: '';
  position: absolute;
  right: var(--space-3);
  bottom: -1px;
  left: var(--space-3);
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: transparent;
}

.ui-tabs__tab--active {
  color: var(--text);
}

.ui-tabs__tab--active::after {
  background: var(--brand);
}

.ui-tabs__count {
  padding: 0 7px;
  border-radius: var(--r-pill);
  background: var(--surface-subtle);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: var(--fw-semibold);
}
</style>
