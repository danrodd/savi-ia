<script setup lang="ts">
import { KpiCard, type Tone } from '@savi/ui'
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
}>()

const definitions = useDefinitions()
const help = computed(() => (props.metric ? definitions.value[props.metric] : undefined))
</script>

<template>
  <KpiCard :label="label" :value="value" :hint="hint" :help="help" :tone="tone" :icon="icon" />
</template>
