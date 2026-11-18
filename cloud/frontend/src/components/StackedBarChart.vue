<script setup lang="ts">
import { computed, ref } from 'vue'

export interface StackSeries {
  key: string
  label: string
  /** Variable CSS del color (`--chart-1`…). El orden es fijo: el color sigue al cliente. */
  color: string
}

export interface StackDay {
  label: string
  values: Record<string, number>
}

const props = withDefaults(
  defineProps<{
    series: StackSeries[]
    days: StackDay[]
    height?: number
    format?: (value: number) => string
  }>(),
  { height: 180, format: (value: number) => String(value) },
)

const WIDTH = 600
const PAD_LEFT = 36
const PAD_TOP = 10
const PAD_BOTTOM = 22
// Separación de superficie entre segmentos: así no dependen solo del color.
const GAP = 2

const totals = computed(() =>
  props.days.map((d) => props.series.reduce((sum, s) => sum + (d.values[s.key] ?? 0), 0)),
)
const max = computed(() => niceMax(Math.max(1, ...totals.value)))
const usable = computed(() => props.height - PAD_TOP - PAD_BOTTOM)
const slot = computed(() => (props.days.length ? (WIDTH - PAD_LEFT) / props.days.length : WIDTH))

const columns = computed(() =>
  props.days.map((day, index) => {
    const x = PAD_LEFT + index * slot.value + slot.value * 0.15
    const width = slot.value * 0.7
    let base = props.height - PAD_BOTTOM
    const segments = props.series
      .map((s) => ({ series: s, value: day.values[s.key] ?? 0 }))
      .filter((seg) => seg.value > 0)
      .map((seg, position) => {
        const full = (seg.value / max.value) * usable.value
        const gap = position === 0 ? 0 : Math.min(GAP, full / 2)
        const h = Math.max(0, full - gap)
        base -= full
        return { ...seg, x, width, y: base, h }
      })
    return { day, index, x, width, segments, total: totals.value[index] ?? 0 }
  }),
)

const ticks = computed(() => [0, max.value / 2, max.value])
const every = computed(() => Math.max(1, Math.ceil(props.days.length / 8)))

const hovered = ref<number | null>(null)
const active = computed(() => (hovered.value === null ? null : columns.value[hovered.value]))
const tipLeft = computed(() => {
  if (!active.value) return '0%'
  const center = (active.value.x + active.value.width / 2) / WIDTH
  return `${Math.min(80, Math.max(20, center * 100))}%`
})

/** Tope del eje redondeado (1, 1,5, 2, 2,5, 5 × 10ⁿ) para que las marcas sean números limpios. */
function niceMax(value: number): number {
  const exp = 10 ** Math.floor(Math.log10(value))
  const step = [1, 1.5, 2, 2.5, 5, 10].find((m) => m * exp >= value) ?? 10
  return step * exp
}

function y(value: number): number {
  return props.height - PAD_BOTTOM - (value / max.value) * usable.value
}
</script>

<template>
  <div v-if="days.length" class="stack-chart">
    <ul class="legend" aria-label="Leyenda">
      <li v-for="s in series" :key="s.key">
        <span class="swatch" :style="{ background: `var(${s.color})` }" aria-hidden="true" />
        {{ s.label }}
      </li>
    </ul>
    <div class="plot" @mouseleave="hovered = null">
      <svg
        :viewBox="`0 0 ${WIDTH} ${height}`"
        role="img"
        :aria-label="`Turnos por día y por cliente: ${series.map((s) => s.label).join(', ')}`"
        class="chart"
        preserveAspectRatio="none"
      >
        <g class="axis">
          <template v-for="tick in ticks" :key="tick">
            <line :x1="PAD_LEFT" :x2="WIDTH" :y1="y(tick)" :y2="y(tick)" class="grid" />
            <text :x="PAD_LEFT - 6" :y="y(tick) + 3" text-anchor="end" class="tick">{{ format(tick) }}</text>
          </template>
        </g>
        <g
          v-for="col in columns"
          :key="col.day.label"
          class="column"
          :class="{ 'column--dim': hovered !== null && hovered !== col.index }"
          @mouseenter="hovered = col.index"
        >
          <!-- Zona de captura de todo el alto: más grande que la barra. -->
          <rect :x="col.x - slot * 0.15" :y="0" :width="slot" :height="height - PAD_BOTTOM" class="hit" />
          <rect
            v-for="seg in col.segments"
            :key="seg.series.key"
            :x="seg.x"
            :y="seg.y"
            :width="seg.width"
            :height="seg.h"
            rx="2"
            :style="{ fill: `var(${seg.series.color})` }"
          />
          <text
            v-if="col.index % every === 0"
            :x="col.x + col.width / 2"
            :y="height - 6"
            text-anchor="middle"
            class="tick"
          >
            {{ col.day.label }}
          </text>
        </g>
      </svg>
      <div v-if="active" class="tip" :style="{ left: tipLeft }" role="status" data-test="stack-tip">
        <strong>{{ active.day.label }} · {{ format(active.total) }}</strong>
        <ul>
          <li v-for="s in series" :key="s.key">
            <span class="swatch" :style="{ background: `var(${s.color})` }" aria-hidden="true" />
            <span class="tip-name">{{ s.label }}</span>
            <span class="num">{{ format(active.day.values[s.key] ?? 0) }}</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
  <p v-else class="muted">Sin datos en el período.</p>
</template>

<style scoped>
.stack-chart {
  display: grid;
  gap: var(--space-3);
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12.5px;
  color: var(--text-muted);
}

.legend li,
.tip li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: none;
}

.plot {
  position: relative;
}

.chart {
  display: block;
  width: 100%;
  height: auto;
  max-height: 240px;
}

.grid {
  stroke: var(--border);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.tick {
  fill: var(--text-muted);
  font-size: 10px;
}

.hit {
  fill: transparent;
}

.column rect:not(.hit) {
  transition: opacity 120ms ease;
}

.column--dim rect:not(.hit) {
  opacity: 0.45;
}

.tip {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  min-width: 180px;
  padding: var(--space-2) var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  font-size: 12px;
  pointer-events: none;
}

.tip ul {
  display: grid;
  gap: 4px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}

.tip li {
  display: grid;
  grid-template-columns: 10px 1fr auto;
}

.tip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted);
}
</style>
