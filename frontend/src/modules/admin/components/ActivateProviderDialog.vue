<script setup lang="ts">
import { TriangleAlert } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import type { LlmProvider } from '../types'
import ProviderIcon from './ProviderIcon.vue'

const props = defineProps<{ open: boolean; provider: LlmProvider | null; activating?: boolean }>()
const emit = defineEmits<{ 'update:open': [boolean]; confirm: [] }>()
</script>

<template>
  <Dialog :open="open" :title="`Activar ${provider?.display_name ?? 'proveedor'}`" :max-width="480" @update:open="emit('update:open', $event)">
    <template #leading>
      <ProviderIcon v-if="provider" :kind="provider.provider" :size="24" />
    </template>
    <p class="activate__warning">
      <TriangleAlert :size="16" aria-hidden="true" />
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
.activate__warning { display: flex; align-items: flex-start; gap: var(--space-3); margin: 0; padding: var(--space-4); color: var(--text); background: var(--brand-soft); border: 1px solid var(--brand); border-radius: var(--r-md); line-height: 1.6; }
.activate__warning svg { flex: none; margin-top: 2px; color: var(--warning); }
.activate__note { margin: var(--space-4) 0 0; color: var(--text-muted); font-size: 13px; }
</style>
