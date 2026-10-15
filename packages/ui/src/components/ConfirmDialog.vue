<script setup lang="ts">
import { ref, watch } from 'vue'
import Button from './Button.vue'
import Dialog from './Dialog.vue'

/**
 * Diálogo de confirmación reutilizable. Reemplazo directo de window.confirm()
 * con accesibilidad y estilos consistentes.
 *
 * Soporta confirmación asíncrona — si `onConfirm` devuelve una promesa, el
 * botón muestra estado loading y el diálogo se cierra al resolverla.
 *
 * Uso:
 *   <ConfirmDialog
 *     v-model:open="open"
 *     title="Eliminar conversación"
 *     description="Esta acción no se puede deshacer."
 *     confirm-label="Eliminar"
 *     variant="danger"
 *     :on-confirm="handleDelete"
 *   />
 */

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    confirmLabel?: string
    cancelLabel?: string
    variant?: 'primary' | 'danger'
    onConfirm?: () => void | Promise<void>
  }>(),
  {
    confirmLabel: 'Confirmar',
    cancelLabel: 'Cancelar',
    variant: 'primary',
  },
)
const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: []
  cancel: []
}>()

const loading = ref(false)

watch(
  () => props.open,
  (open) => {
    if (!open) loading.value = false
  },
)

async function handleConfirm(): Promise<void> {
  if (loading.value) return
  emit('confirm')
  if (!props.onConfirm) {
    emit('update:open', false)
    return
  }
  loading.value = true
  try {
    await props.onConfirm()
    emit('update:open', false)
  } catch {
    // el llamador debe mostrar feedback (toast); dejamos el diálogo abierto
    // por si quiere reintentar
  } finally {
    loading.value = false
  }
}

function handleCancel(): void {
  emit('cancel')
  emit('update:open', false)
}
</script>

<template>
  <Dialog
    :open="open"
    :title="title"
    :description="description"
    :max-width="420"
    @update:open="$emit('update:open', $event)"
  >
    <template #footer>
      <Button variant="ghost" :disabled="loading" @click="handleCancel">
        {{ cancelLabel }}
      </Button>
      <Button :variant="variant" :loading="loading" @click="handleConfirm">
        {{ confirmLabel }}
      </Button>
    </template>
  </Dialog>
</template>
