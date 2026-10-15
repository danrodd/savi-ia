<script setup lang="ts">
import { Alert, Button, CopyField, Dialog } from '@savi/ui'

/**
 * Muestra un secreto (token de vinculación, contraseña temporal) una sola vez. No se
 * cierra tocando afuera ni con Escape: solo con "Ya lo guardé", para que nadie lo pierda
 * por un clic accidental.
 */
defineProps<{
  open: boolean
  title: string
  /** El valor que se muestra una sola vez (token o contraseña temporal). */
  secret: string
  instructions: string
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <Dialog :open="open" :title="title" :max-width="520" :close-on-overlay="false" :show-close="false" @update:open="() => undefined">
    <div class="secret">
      <Alert tone="warning">
        Se muestra <strong>una sola vez</strong>. Al cerrar esta ventana no se puede volver a ver.
      </Alert>
      <CopyField :value="secret" label="Valor" data-test="secret" />
      <p class="secret__instructions">{{ instructions }}</p>
    </div>
    <template #footer>
      <Button data-test="secret-close" @click="emit('close')">Ya lo guardé</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.secret {
  display: grid;
  gap: var(--space-4);
}

.secret__instructions {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
