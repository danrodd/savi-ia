<script setup lang="ts">
import { Button, Dialog, Textarea } from '@savi/ui'
import type { AlertActions } from '@/composables/useAlertActions'
import { useRuleTitles } from '@/lib/ruleTitles'

defineProps<{ actions: AlertActions }>()
const ruleTitle = useRuleTitles()

function describe(actions: AlertActions): string {
  const many = actions.resolvingMany.value
  if (many)
    return many.length === 1 ? '1 alerta seleccionada' : `${many.length} alertas seleccionadas`
  return actions.resolving.value ? ruleTitle(actions.resolving.value.rule_code) : ''
}
</script>

<template>
  <Dialog
    :open="actions.resolving.value !== null || actions.resolvingMany.value !== null"
    :title="actions.resolvingMany.value ? 'Resolver alertas' : 'Resolver alerta'"
    :description="describe(actions)"
    :max-width="480"
    @update:open="(open) => !open && actions.closeResolve()"
  >
    <Textarea
      v-model="actions.note.value"
      label="Nota"
      placeholder="Qué se hizo (opcional)"
      :rows="3"
      :maxlength="500"
      :hint="
        actions.resolvingMany.value
          ? 'Se aplica a todas y queda en la auditoría junto con quién las resolvió.'
          : 'Queda en la auditoría junto con quién la resolvió.'
      "
    />
    <template #footer>
      <Button
        variant="ghost"
        :disabled="actions.resolveBusy.value"
        @click="actions.closeResolve()"
      >
        Cancelar
      </Button>
      <Button
        :loading="actions.resolveBusy.value"
        data-test="resolve-confirm"
        @click="actions.resolve()"
      >
        {{ actions.resolvingMany.value ? 'Resolver alertas' : 'Resolver alerta' }}
      </Button>
    </template>
  </Dialog>
</template>
