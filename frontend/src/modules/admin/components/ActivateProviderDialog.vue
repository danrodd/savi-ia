<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import type { LlmProvider } from '../types'

const props = defineProps<{ open: boolean; provider: LlmProvider | null; activating?: boolean }>()
const emit = defineEmits<{ 'update:open': [boolean]; confirm: [] }>()
</script>

<template>
  <Dialog :open="open" :title="`Activar ${provider?.display_name ?? 'proveedor'}`" :max-width="480" @update:open="emit('update:open', $event)">
    <p class="activate__warning">
      A partir del próximo mensaje, las preguntas de los usuarios y los datos del ERP que SAVI consulte para responderlas se van a enviar al nuevo proveedor.
    </p>
    <p class="activate__note">Las conversaciones anteriores no cambian.</p>
    <template #footer>
      <Button variant="ghost" :disabled="activating" @click="emit('update:open', false)">Cancelar</Button>
      <Button :loading="activating" @click="emit('confirm')">Activar</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.activate__warning { margin: 0; padding: var(--space-4); color: var(--text); background: var(--brand-soft); border: 1px solid var(--brand); border-radius: var(--r-md); line-height: 1.6; }
.activate__note { margin: var(--space-4) 0 0; color: var(--text-muted); font-size: 13px; }
</style>
