<script setup lang="ts">
import { Button, Dialog, TextField } from '@savi/ui'
import { computed, ref, watch } from 'vue'

/**
 * Confirmación de acciones sensibles de la consola, sobre el `Dialog` compartido. Agrega
 * lo que la consola necesita: el padre controla `busy` (la acción la ejecuta él) y, para
 * lo irreversible, `typeToConfirm` obliga a escribir una palabra exacta.
 */
const props = defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel: string
  danger?: boolean
  /** Si se define, hay que escribir exactamente este texto para habilitar el botón. */
  typeToConfirm?: string
  busy?: boolean
}>()

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const typed = ref('')
watch(
  () => props.open,
  () => {
    typed.value = ''
  },
)

const canConfirm = computed(
  () => !props.busy && (!props.typeToConfirm || typed.value === props.typeToConfirm),
)

function onOpenChange(open: boolean): void {
  if (!open && !props.busy) emit('cancel')
}
</script>

<template>
  <Dialog :open="open" :title="title" :description="message" :max-width="460" @update:open="onOpenChange">
    <TextField
      v-if="typeToConfirm"
      v-model="typed"
      :label="`Para continuar escriba ${typeToConfirm}`"
      autocomplete="off"
      mono
      data-test="type-to-confirm"
    />
    <template #footer>
      <Button variant="ghost" :disabled="busy" data-test="confirm-cancel" @click="emit('cancel')">
        Cancelar
      </Button>
      <Button
        :variant="danger ? 'danger' : 'primary'"
        :loading="busy"
        :disabled="!canConfirm"
        data-test="confirm-accept"
        @click="emit('confirm')"
      >
        {{ confirmLabel }}
      </Button>
    </template>
  </Dialog>
</template>
