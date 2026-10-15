<script setup lang="ts">
import { Badge } from '@savi/ui'
import { badgeTone, type Tone } from '@/lib/format'

/** Estado con los tonos de la consola (`ok`, `warn`, `bad`, `muted`) sobre el `Badge` compartido. */
defineProps<{ tone: Tone; label: string }>()
</script>

<template>
  <Badge :tone="badgeTone(tone)" dot>{{ label }}</Badge>
</template>
