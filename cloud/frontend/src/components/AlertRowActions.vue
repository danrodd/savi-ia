<script setup lang="ts">
import { Button } from '@savi/ui'
import type { AlertActions } from '@/composables/useAlertActions'
import type { Alert } from '@/lib/types'

defineProps<{ alert: Alert; actions: AlertActions }>()
</script>

<template>
  <div v-if="actions.canManage(alert)" class="actions">
    <Button
      v-if="alert.status === 'open'"
      variant="secondary"
      size="sm"
      :loading="actions.busyId.value === alert.id"
      @click="actions.acknowledge(alert)"
    >
      Reconocer
    </Button>
    <Button variant="secondary" size="sm" @click="actions.openResolve(alert)">Resolver</Button>
  </div>
</template>

<style scoped>
.actions {
  display: inline-flex;
  gap: var(--space-2);
}
</style>
