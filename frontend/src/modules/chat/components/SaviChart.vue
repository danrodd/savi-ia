<script setup lang="ts">
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import Tooltip from '@/components/ui/Tooltip.vue'
import { type ChartSpec, parseChartSpec } from '@/lib/chartSpec'
import { slugify, triggerDownload } from '@/lib/download'
import DownloadButton from './DownloadButton.vue'

// Registro tree-shakeable: solo los charts/componentes que usamos. Este módulo
// se carga lazy (ver MarkdownRenderer), así que ECharts no entra al bundle base.
use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  CanvasRenderer,
])

const props = defineProps<{ source: string }>()

const parsed = computed(() => parseChartSpec(props.source))

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function palette(): { text: string; muted: string; border: string; series: string[] } {
  const brand = cssVar('--brand', '#4f46e5')
  return {
    text: cssVar('--text', '#1a1a1a'),
    muted: cssVar('--text-muted', '#6b7280'),
    border: cssVar('--border', '#e5e7eb'),
    series: [brand, '#22c55e', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6'],
  }
}

function buildOption(spec: ChartSpec): Record<string, unknown> {
  const p = palette()
  const title = spec.title
    ? { text: spec.title, left: 'center', textStyle: { color: p.text, fontSize: 14 } }
    : undefined

  if (spec.type === 'pie') {
    const labels = spec.labels ?? []
    const values = spec.series[0]?.data ?? []
    const data = values.map((value, i) => ({ value, name: labels[i] ?? `#${i + 1}` }))
    return {
      title,
      color: p.series,
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, textStyle: { color: p.muted } },
      series: [
        {
          type: 'pie',
          radius: ['42%', '70%'],
          center: ['50%', title ? '54%' : '46%'],
          data,
          label: { color: p.text },
          itemStyle: { borderColor: cssVar('--surface', '#fff'), borderWidth: 2 },
        },
      ],
    }
  }

  const isArea = spec.type === 'area'
  const seriesType = isArea ? 'line' : spec.type
  const multi = spec.series.length > 1
  return {
    title,
    color: p.series,
    tooltip: { trigger: 'axis' },
    legend: multi ? { bottom: 0, textStyle: { color: p.muted } } : undefined,
    grid: {
      left: 8,
      right: 16,
      top: title ? 40 : 16,
      bottom: multi ? 32 : 8,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: spec.labels ?? [],
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted },
    },
    series: spec.series.map((s) => ({
      name: s.name,
      type: seriesType,
      data: s.data,
      stack: spec.stacked ? 'total' : undefined,
      areaStyle: isArea ? {} : undefined,
      smooth: seriesType === 'line',
      itemStyle: { borderRadius: spec.type === 'bar' ? [4, 4, 0, 0] : 0 },
    })),
  }
}

const option = computed(() => (parsed.value.ok ? buildOption(parsed.value.spec) : null))

const chart = ref<InstanceType<typeof VChart> | null>(null)

function download(): void {
  const inst = chart.value
  if (!inst) return
  const url = inst.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: cssVar('--surface-elev', '#ffffff'),
  })
  const title = parsed.value.ok ? parsed.value.spec.title : undefined
  triggerDownload(url, `${slugify(title ?? 'grafica', 'grafica')}.png`)
}
</script>

<template>
  <figure v-if="option" class="savi-chart">
    <Tooltip text="Descargar PNG" side="right">
      <DownloadButton class="savi-chart__download" label="Descargar PNG" @click="download" />
    </Tooltip>
    <VChart ref="chart" class="savi-chart__canvas" :option="option" autoresize />
  </figure>
  <!-- Degradación elegante: spec inválido → mostramos los datos crudos. -->
  <pre v-else class="savi-chart__fallback"><code>{{ source }}</code></pre>
</template>

<style scoped>
.savi-chart {
  position: relative;
  margin: 0 0 12px;
  padding: var(--space-4);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-xs);
}

.savi-chart__download {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  z-index: 1;
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.savi-chart:hover .savi-chart__download,
.savi-chart:focus-within .savi-chart__download {
  opacity: 1;
}

/* En pantallas táctiles (sin hover) el botón queda siempre visible. */
@media (hover: none) {
  .savi-chart__download {
    opacity: 1;
  }
}

.savi-chart__canvas {
  width: 100%;
  height: 320px;
}

.savi-chart__fallback {
  margin: 0 0 12px;
  padding: var(--space-4) var(--space-5);
  background: var(--surface-sidebar);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
