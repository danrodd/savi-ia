<script setup lang="ts">
/**
 * Barra apilada de costo por día, una serie por proveedor. Es lo que
 * permite "ver qué pasó" en un pico: un día alto en un solo color es un
 * proveedor con un problema puntual, no un aumento general.
 */
import { computed } from 'vue'
import type { DailyProviderUsage } from '../types'
import { formatCopAmount, formatDay } from '../utils/format'
import { PROVIDER_LABELS } from '../utils/providers'
import UsageChart from './UsageChart.vue'

const props = defineProps<{
  daily: DailyProviderUsage[]
  rate: number
}>()

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

// Paleta de marca por proveedor cuando se conoce; genérica para el resto.
const PROVIDER_COLORS: Record<string, string> = {
  claude: '#d97757',
  gemini: '#4285f4',
  openai: '#10a37f',
}

const option = computed<Record<string, unknown>>(() => {
  const muted = cssVar('--text-muted', '#6b7280')
  const border = cssVar('--border', '#e5e7eb')
  const days = [...new Set(props.daily.map((d) => d.day))].sort()
  const providers = [...new Set(props.daily.map((d) => d.provider ?? 'sin-proveedor'))]

  const byDayAndProvider = new Map<string, number>()
  for (const row of props.daily) {
    byDayAndProvider.set(`${row.day}|${row.provider ?? 'sin-proveedor'}`, row.totals.cost_usd)
  }

  return {
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number) => formatCopAmount(v),
    },
    legend: { textStyle: { color: muted }, top: 0 },
    grid: { left: 64, right: 16, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: days.map((d) => formatDay(d)),
      axisLabel: { color: muted },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: muted, formatter: (v: number) => formatCopAmount(v) },
      splitLine: { lineStyle: { color: border } },
    },
    series: providers.map((provider) => ({
      name: PROVIDER_LABELS[provider as keyof typeof PROVIDER_LABELS] ?? provider,
      type: 'bar',
      stack: 'costo',
      itemStyle: { color: PROVIDER_COLORS[provider] },
      data: days.map((day) => {
        const usd = byDayAndProvider.get(`${day}|${provider}`) ?? 0
        return Math.round(usd * props.rate)
      }),
    })),
  }
})
</script>

<template>
  <UsageChart :option="option" :height="280" />
</template>
