<script setup lang="ts">
import {
  Badge,
  Button,
  Card,
  DataTable,
  Select,
  type TableColumn,
  type Tone,
  toast,
} from '@savi/ui'
import { KeyRound } from 'lucide-vue-next'
import { ref } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SecretDialog from '@/components/SecretDialog.vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { EnrollmentToken } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; tokens: EnrollmentToken[]; loading: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const DURATIONS = [
  { value: 24, label: '24 horas' },
  { value: 72, label: '3 días' },
  { value: 168, label: '7 días (máximo)' },
]

const TOKEN_STATE: Record<string, { label: string; tone: Tone }> = {
  pending: { label: 'Vigente', tone: 'success' },
  used: { label: 'Usado', tone: 'neutral' },
  expired: { label: 'Vencido', tone: 'warning' },
  revoked: { label: 'Revocado', tone: 'danger' },
}

const COLUMNS: TableColumn[] = [
  { key: 'state', label: 'Estado', width: '120px' },
  { key: 'created_at', label: 'Creado' },
  { key: 'expires_at', label: 'Vence' },
  { key: 'created_by', label: 'Creado por' },
  { key: 'actions', label: '', align: 'right', width: '110px' },
]

const expiresHours = ref<number | null>(72)
const creating = ref(false)
const createdToken = ref<string | null>(null)
const revoking = ref<EnrollmentToken | null>(null)
const busy = ref(false)

async function createToken(): Promise<void> {
  creating.value = true
  try {
    const created = await consoleApi.createToken(props.clientId, expiresHours.value ?? 72)
    createdToken.value = created.token
  } catch (e) {
    toast.error('No se pudo generar el token', { description: errorMessage(e) })
  } finally {
    creating.value = false
  }
}

function closeToken(): void {
  // El token ya no se puede recuperar: se descarta de memoria al cerrar.
  createdToken.value = null
  emit('changed')
}

async function revokeToken(): Promise<void> {
  const token = revoking.value
  if (!token) return
  busy.value = true
  try {
    await consoleApi.revokeToken(token.id)
    toast.success('Token revocado')
    emit('changed')
  } catch (e) {
    toast.error('No se pudo revocar el token', { description: errorMessage(e) })
  } finally {
    busy.value = false
    revoking.value = null
  }
}
</script>

<template>
  <div class="tokens">
    <Card
      title="Vincular una instalación"
      description="El token se pega en SAVI → Administración → SAVI Cloud, o en el instalador. Se muestra una sola vez y sirve para una sola instalación."
    >
      <div class="tokens__create">
        <Select v-model="expiresHours" label="Vigencia" :options="DURATIONS" data-test="token-duration" />
        <Button :loading="creating" class="tokens__button" data-test="token-create" @click="createToken">
          <KeyRound :size="15" aria-hidden="true" />
          Generar token de vinculación
        </Button>
      </div>
    </Card>

    <Card title="Tokens generados" padding="none">
      <DataTable
        :columns="COLUMNS"
        :rows="tokens"
        row-key="id"
        :loading="loading"
        caption="Tokens de vinculación"
        empty-text="Todavía no se generó ningún token."
      >
        <template #cell-state="{ row }">
          <Badge :tone="TOKEN_STATE[row.state]?.tone ?? 'neutral'" dot>
            {{ TOKEN_STATE[row.state]?.label ?? row.state }}
          </Badge>
        </template>
        <template #cell-created_at="{ row }">{{ formatDateTime(row.created_at) }}</template>
        <template #cell-expires_at="{ row }">{{ formatDateTime(row.expires_at) }}</template>
        <template #cell-actions="{ row }">
          <Button
            v-if="row.state === 'pending'"
            variant="ghost"
            size="sm"
            data-test="token-revoke"
            @click="revoking = row"
          >
            Revocar
          </Button>
        </template>
      </DataTable>
    </Card>
  </div>

  <SecretDialog
    :open="createdToken !== null"
    title="Token de vinculación"
    :secret="createdToken ?? ''"
    instructions="Pegalo en SAVI → Administración → SAVI Cloud, o en el instalador."
    @close="closeToken"
  />

  <ConfirmDialog
    :open="revoking !== null"
    title="Revocar el token"
    message="La instalación que todavía no lo usó ya no podrá vincularse con este token. Si hace falta, generá uno nuevo."
    confirm-label="Revocar"
    danger
    :busy="busy"
    @confirm="revokeToken"
    @cancel="revoking = null"
  />
</template>

<style scoped>
.tokens {
  display: grid;
  gap: var(--space-6);
}

.tokens__create {
  display: grid;
  grid-template-columns: minmax(0, 240px) auto;
  align-items: start;
  gap: var(--space-4);
}

.tokens__button {
  margin-top: 21px;
}

@media (max-width: 600px) {
  .tokens__create {
    grid-template-columns: minmax(0, 1fr);
  }

  .tokens__button {
    margin-top: 0;
  }
}
</style>
