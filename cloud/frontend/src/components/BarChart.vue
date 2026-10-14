<script setup lang="ts">
import { computed } from 'vue'

export interface BarDatum {
  label: string
  value: number
}

const props = withDefaults(
  defineProps<{ data: BarDatum[]; height?: number; format?: (value: number) => string }>(),
  { height: 140, format: (value: number) => String(value) },
)

const WIDTH = 600
const PAD_TOP = 8
const PAD_BOTTOM = 22

const max = computed(() => Math.max(1, ...props.data.map((d) => d.value)))
const slot = computed(() => (props.data.length ? WIDTH / props.data.length : WIDTH))
const bars = computed(() =>
  props.data.map((d, index) => {
    const usable = props.height - PAD_TOP - PAD_BOTTOM
    const h = (d.value / max.value) * usable
    return {
      ...d,
      x: index * slot.value + slot.value * 0.15,
      width: slot.value * 0.7,
      y: props.height - PAD_BOTTOM - h,
      h,
    }
  }),
)
// Con muchos días solo se rotula una de cada N para que no se pisen.
const every = computed(() => Math.max(1, Math.ceil(props.data.length / 8)))
</script>

<template>
  <svg
    v-if="data.length"
    :viewBox="`0 0 ${WIDTH} ${height}`"
    role="img"
    aria-label="Gráfico de barras"
    class="chart"
    preserveAspectRatio="none"
  >
    <g v-for="(bar, index) in bars" :key="bar.label">
      <rect :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.h" rx="3" class="bar">
        <title>{{ bar.label }}: {{ format(bar.value) }}</title>
      </rect>
      <text
        v-if="index % every === 0"
        :x="bar.x + bar.width / 2"
        :y="height - 6"
        text-anchor="middle"
        class="tick"
      >
        {{ bar.label }}
      </text>
    </g>
  </svg>
  <p v-else class="muted">Sin datos en el período.</p>
</template>

<style scoped>
.chart {
  width: 100%;
  height: auto;
  max-height: 220px;
}
.bar {
  fill: var(--accent);
  opacity: 0.85;
}
.bar:hover {
  opacity: 1;
}
.tick {
  fill: var(--text-muted);
  font-size: 10px;
}
</style>
