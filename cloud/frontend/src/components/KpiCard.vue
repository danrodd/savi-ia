<script setup lang="ts">
import { KpiCard, type Tone } from '@savi/ui'
import { Minus, TrendingDown, TrendingUp } from 'lucide-vue-next'
import { type Component, computed } from 'vue'
import { useDefinitions } from '@/lib/definitions'

/** Indicador de la consola: agrega la definición única de la métrica (`metric-definitions`). */
const props = defineProps<{
  label: string
  value: string
  /** Clave de `metric-definitions`: muestra la definición de la métrica como ayuda. */
  metric?: string
  hint?: string
  tone?: Tone
  icon?: Component
  /**
   * Variación frente al periodo anterior. Va en tono neutro: que suba el costo o
   * los turnos no es bueno ni malo por sí mismo, y el rojo queda para lo crítico.
   */
  change?: { text: string; direction: 'up' | 'down' | 'flat' } | null
}>()

const definitions = useDefinitions()
const help = computed(() => (props.metric ? definitions.value[props.metric] : undefined))
const changeIcon = computed(() =>
  props.change?.direction === 'up'
    ? TrendingUp
    : props.change?.direction === 'down'
      ? TrendingDown
      : Minus,
)
</script>

<template>
  <KpiCard :label="label" :value="value" :hint="hint" :help="help" :tone="tone" :icon="icon">
    <template v-if="change" #hint>
      <span class="change" data-test="kpi-change">
        <component :is="changeIcon" :size="13" aria-hidden="true" />
        <strong>{{ change.text }}</strong>
        <span>frente a los 30 días anteriores</span>
      </span>
    </template>
  </KpiCard>
</template>

<style scoped>
.change {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.change strong {
  color: var(--text);
  font-weight: var(--fw-medium);
}
</style>
