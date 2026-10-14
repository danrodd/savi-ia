<script setup lang="ts">
import { computed } from 'vue'
import { freshnessLabel, freshnessTone } from '@/lib/format'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ seconds: number | null }>()

const tone = computed(() => freshnessTone(props.seconds))
const label = computed(() => freshnessLabel(props.seconds))
</script>

<template>
  <StatusBadge
    :tone="tone"
    :label="label"
    title="Las cifras llegan hasta este momento. Si la instalación estuvo sin conexión, el uso parece menor de lo real."
  />
</template>
