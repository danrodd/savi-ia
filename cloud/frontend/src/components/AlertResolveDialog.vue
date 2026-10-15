<script setup lang="ts">
import { Button, Dialog, Textarea } from '@savi/ui'
import type { AlertActions } from '@/composables/useAlertActions'
import { useRuleTitles } from '@/lib/ruleTitles'

defineProps<{ actions: AlertActions }>()
const ruleTitle = useRuleTitles()
</script>

<template>
  <Dialog
    :open="actions.resolving.value !== null"
    title="Resolver alerta"
    :description="actions.resolving.value ? ruleTitle(actions.resolving.value.rule_code) : ''"
    :max-width="480"
    @update:open="(open) => !open && (actions.resolving.value = null)"
  >
    <Textarea
      v-model="actions.note.value"
      label="Nota"
      placeholder="Qué se hizo (opcional)"
      :rows="3"
      :maxlength="500"
      hint="Queda en la auditoría junto con quién la resolvió."
    />
    <template #footer>
      <Button
        variant="ghost"
        :disabled="actions.resolveBusy.value"
        @click="actions.resolving.value = null"
      >
        Cancelar
      </Button>
      <Button
        :loading="actions.resolveBusy.value"
        data-test="resolve-confirm"
        @click="actions.resolve()"
      >
        Resolver alerta
      </Button>
    </template>
  </Dialog>
</template>
