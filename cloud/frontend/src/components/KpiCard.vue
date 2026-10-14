<script setup lang="ts">
import { computed } from 'vue'
import { useDefinitions } from '@/lib/definitions'

const props = defineProps<{
  label: string
  value: string
  /** Clave de `metric-definitions`: muestra la definición única de la métrica. */
  metric?: string
  hint?: string
}>()

const definitions = useDefinitions()
const help = computed(() => (props.metric ? definitions.value[props.metric] : undefined))
</script>

<template>
  <div class="card kpi">
    <div class="label">
      {{ label }}
      <span v-if="help" class="help" :title="help" role="img" :aria-label="`Definición: ${help}`">?</span>
    </div>
    <div class="value">{{ value }}</div>
    <div v-if="hint" class="muted hint">{{ hint }}</div>
  </div>
</template>

<style scoped>
.kpi {
  display: grid;
  gap: 0.15rem;
}
.label {
  color: var(--text-muted);
  font-size: 0.82rem;
}
.value {
  font-size: 1.6rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.hint {
  font-size: 0.8rem;
}
.help {
  display: inline-grid;
  place-items: center;
  width: 1.05rem;
  height: 1.05rem;
  margin-left: 0.2rem;
  border: 1px solid var(--border);
  border-radius: 50%;
  font-size: 0.7rem;
  cursor: help;
}
</style>
