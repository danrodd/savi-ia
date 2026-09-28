<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { toast } from '@/lib/toast'
import { useWebSourceStore } from '../stores/webSourceStore'
import type { WebSource } from '../types'
import WebSourceDetailDialog from './WebSourceDetailDialog.vue'
import WebSourceEditDialog from './WebSourceEditDialog.vue'
import WebSourceList from './WebSourceList.vue'

defineProps<{
  databaseNames: Record<string, string>
  databases: { id: string; name: string }[]
}>()
const emit = defineEmits<{ add: [] }>()

const store = useWebSourceStore()
const busyId = ref<string | null>(null)
const removing = ref<WebSource | null>(null)
const editing = ref<WebSource | null>(null)
const detailId = ref<string | null>(null)

const editOpen = computed({
  get: () => editing.value !== null,
  set: (open: boolean) => {
    if (!open) editing.value = null
  },
})

const detailOpen = computed({
  get: () => detailId.value !== null,
  set: (open: boolean) => {
    if (!open) detailId.value = null
  },
})

const removeOpen = computed({
  get: () => removing.value !== null,
  set: (open: boolean) => {
    if (!open) removing.value = null
  },
})

async function withBusy(source: WebSource, action: () => Promise<void>): Promise<void> {
  busyId.value = source.id
  try {
    await action()
  } finally {
    busyId.value = null
  }
}

function onRefresh(source: WebSource): void {
  void withBusy(source, async () => {
    try {
      await store.refreshNow(source.id)
      toast.success(`${source.title}: se va a leer de nuevo`)
    } catch (e) {
      toast.error((e as Error).message || 'No se pudo pedir la lectura.')
    }
  })
}

async function onConfirmRemove(): Promise<void> {
  const source = removing.value
  if (!source) return
  await withBusy(source, async () => {
    await store.remove(source.id)
    toast.success(`${source.title} eliminado`)
  })
}

onMounted(() => {
  void store.load()
  store.startPolling()
})

onUnmounted(() => store.stopPolling())
</script>

<template>
  <div>
    <p v-if="store.error" class="wpanel__error" role="alert">
      {{ store.error }}
      <button type="button" class="wpanel__retry" @click="store.load()">Reintentar</button>
    </p>
    <p v-else-if="!store.loaded" class="wpanel__hint">Cargando…</p>
    <div v-else-if="store.sources.length === 0" class="wpanel__empty">
      <p>
        Aún no hay sitios web. Agrega la página de la empresa para que SAVI responda con lo que
        publica —precios, horarios, políticas— y cite el link.
      </p>
      <!-- Texto distinto al del encabezado: dos botones con el mismo nombre
           accesible en la misma pantalla confunden a un lector de pantalla. -->
      <Button @click="emit('add')">Agregar el primer sitio</Button>
    </div>
    <WebSourceList
      v-else
      :sources="store.sources"
      :database-names="databaseNames"
      :busy-id="busyId"
      @detail="(source) => (detailId = source.id)"
      @edit="(source) => (editing = source)"
      @refresh="onRefresh"
      @remove="(source) => (removing = source)"
    />

    <WebSourceDetailDialog v-model:open="detailOpen" :source-id="detailId" />
    <WebSourceEditDialog v-model:open="editOpen" :source="editing" :databases="databases" />
    <ConfirmDialog
      v-model:open="removeOpen"
      :title="`Eliminar ${removing?.title ?? ''}`"
      description="Se borran todas las páginas leídas de este sitio y dejan de usarse de inmediato. Las respuestas anteriores mostrarán la fuente como eliminada."
      confirm-label="Eliminar"
      variant="danger"
      :on-confirm="onConfirmRemove"
    />
  </div>
</template>

<style scoped>
.wpanel__hint {
  font-size: 13px;
  color: var(--text-muted);
}

.wpanel__empty {
  display: grid;
  justify-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-4);
  border: 1px dashed var(--border);
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}

.wpanel__empty p {
  margin: 0;
  max-width: 60ch;
}

.wpanel__error {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.wpanel__retry {
  background: transparent;
  border: none;
  color: inherit;
  font: inherit;
  font-weight: var(--fw-semibold);
  text-decoration: underline;
  cursor: pointer;
}
</style>
