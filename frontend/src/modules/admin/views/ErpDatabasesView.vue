<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { toast } from '@/lib/toast'
import ErpDatabaseFormDialog from '../components/ErpDatabaseFormDialog.vue'
import ErpDatabaseTable from '../components/ErpDatabaseTable.vue'
import { useErpDatabaseStore } from '../stores/erpDatabaseStore'
import type { ErpDatabase } from '../types'

type PendingAction = 'deactivate' | 'remove'

const store = useErpDatabaseStore()

const formOpen = ref(false)
const editing = ref<ErpDatabase | null>(null)
const busyId = ref<string | null>(null)
const pending = ref<{ action: PendingAction; db: ErpDatabase } | null>(null)

const confirmOpen = computed({
  get: () => pending.value !== null,
  set: (open: boolean) => {
    if (!open) pending.value = null
  },
})

const confirmCopy = computed(() => {
  if (!pending.value) return { title: '', description: '', label: '' }
  const { action, db } = pending.value
  if (action === 'deactivate') {
    return {
      title: `Desactivar ${db.name}`,
      description:
        'No se podrán iniciar conversaciones nuevas ni enviar mensajes contra esta base. El historial se sigue viendo y puedes reactivarla después.',
      label: 'Desactivar',
    }
  }
  return {
    title: `Eliminar ${db.name}`,
    description:
      'La base desaparece del listado y del selector del chat. El historial de sus conversaciones se conserva. Esta acción no se puede deshacer desde la aplicación.',
    label: 'Eliminar',
  }
})

function openCreate(): void {
  editing.value = null
  formOpen.value = true
}

function openEdit(db: ErpDatabase): void {
  editing.value = db
  formOpen.value = true
}

async function run(db: ErpDatabase, action: () => Promise<void>, success: string): Promise<void> {
  busyId.value = db.id
  try {
    await action()
    toast.success(success)
  } catch (e) {
    toast.error((e as Error).message || 'No se pudo completar la acción.')
    throw e
  } finally {
    busyId.value = null
  }
}

function onSetDefault(db: ErpDatabase): void {
  void run(db, () => store.setDefault(db.id), `${db.name} es ahora la base predeterminada`).catch(
    () => undefined,
  )
}

function onActivate(db: ErpDatabase): void {
  void run(db, () => store.activate(db.id), `${db.name} activada`).catch(() => undefined)
}

async function onConfirm(): Promise<void> {
  if (!pending.value) return
  const { action, db } = pending.value
  if (action === 'deactivate') {
    await run(db, () => store.deactivate(db.id), `${db.name} desactivada`)
  } else {
    await run(db, () => store.remove(db.id), `${db.name} eliminada`)
  }
}

onMounted(() => {
  void store.load()
})
</script>

<template>
  <section class="dbview">
    <header class="dbview__header">
      <div>
        <h1 class="dbview__title">Bases de datos</h1>
        <p class="dbview__subtitle">
          Bases del ERP de cada cliente. Cada conversación queda asociada a una base al crearla.
        </p>
      </div>
      <Button @click="openCreate">Nueva base</Button>
    </header>

    <p v-if="store.error" class="dbview__error" role="alert">
      {{ store.error }}
      <button type="button" class="dbview__retry" @click="store.load()">Reintentar</button>
    </p>
    <p v-else-if="store.loading && store.databases.length === 0" class="dbview__hint">Cargando…</p>
    <p v-else-if="store.databases.length === 0" class="dbview__hint">
      Aún no hay bases registradas.
    </p>
    <ErpDatabaseTable
      v-else
      :databases="store.databases"
      :busy-id="busyId"
      @edit="openEdit"
      @set-default="onSetDefault"
      @activate="onActivate"
      @deactivate="(db) => (pending = { action: 'deactivate', db })"
      @remove="(db) => (pending = { action: 'remove', db })"
    />

    <ErpDatabaseFormDialog v-model:open="formOpen" :database="editing" />

    <ConfirmDialog
      v-model:open="confirmOpen"
      :title="confirmCopy.title"
      :description="confirmCopy.description"
      :confirm-label="confirmCopy.label"
      variant="danger"
      :on-confirm="onConfirm"
    />
  </section>
</template>

<style scoped>
.dbview__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.dbview__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.dbview__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 60ch;
  line-height: 1.5;
}

.dbview__hint {
  font-size: 13px;
  color: var(--text-muted);
}

.dbview__error {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.dbview__retry {
  background: transparent;
  border: none;
  color: inherit;
  font: inherit;
  font-weight: var(--fw-semibold);
  text-decoration: underline;
  cursor: pointer;
}
</style>
