<script setup lang="ts">
/**
 * Wrapper genérico de ECharts para la vista de consumo.
 *
 * Registro tree-shakeable (solo lo que usamos). Se carga lazy con la vista
 * de consumo, así ECharts no entra al bundle base.
 *
 * Altura FIJA por prop (no `height: 100%`): en un layout sin alto definido,
 * `height: 100%` + `autoresize` genera un loop de medición que infla la
 * gráfica sin control. Una altura concreta lo corta y deja el scroll sano.
 */
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
])

const props = withDefaults(defineProps<{ option: Record<string, unknown>; height?: number }>(), {
  height: 300,
})
</script>

<template>
  <VChart
    class="usage-chart"
    :option="option"
    :style="{ height: `${props.height}px` }"
    autoresize
  />
</template>

<style scoped>
.usage-chart {
  width: 100%;
}
</style>
