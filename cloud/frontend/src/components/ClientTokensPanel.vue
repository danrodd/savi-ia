<script setup lang="ts">
import {
  Alert,
  Badge,
  Button,
  Card,
  CopyField,
  DataTable,
  Select,
  type StepItem,
  Stepper,
  type TableColumn,
  type Tone,
  toast,
} from '@savi/ui'
import { KeyRound, Loader } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SecretDialog from '@/components/SecretDialog.vue'
import { useNewInstanceWatch } from '@/composables/useNewInstanceWatch'
import { consoleApi } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { EnrollmentToken } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = withDefaults(
  defineProps<{
    clientId: string
    tokens: EnrollmentToken[]
    loading: boolean
    /** Quien no tiene `tokens.manage` ve la lista, pero no puede generar ni revocar. */
    canManage?: boolean
  }>(),
  { canManage: true },
)
const emit = defineEmits<{ changed: [] }>()

const STEPS: StepItem[] = [
  { key: 'generate', label: 'Generar token' },
  { key: 'install', label: 'Instalar SAVI y pegar el token' },
  { key: 'waiting', label: 'Esperando la primera conexión' },
]
const STEPS_LINKED: StepItem[] = [...STEPS, { key: 'linked', label: 'Vinculada' }]

/** Dirección de esta consola: es la de SAVI Cloud (`-SaviCloudUrl` del instalador). */
const cloudUrl = window.location.origin

const watcher = useNewInstanceWatch(() => props.clientId)
const step = ref<'generate' | 'install'>('generate')
const current = computed(() => {
  if (watcher.state.value === 'found') return 'linked'
  if (watcher.state.value === 'waiting' || watcher.state.value === 'timeout') return 'waiting'
  return step.value
})
const steps = computed(() => (watcher.state.value === 'found' ? STEPS_LINKED : STEPS))

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
    watcher.reset()
    await watcher.snapshot()
    createdToken.value = created.token
    step.value = 'install'
  } catch (e) {
    toast.error('No se pudo generar el token', { description: errorMessage(e) })
  } finally {
    creating.value = false
  }
}

function closeToken(): void {
  // El token ya no se puede recuperar: se descarta de memoria al cerrar.
  createdToken.value = null
  step.value = 'generate'
  watcher.start()
  emit('changed')
}

function generateAnother(): void {
  watcher.reset()
}

function keepWaiting(): void {
  watcher.start()
}

// Al vincularse, el token pasa a "Usado": se recarga la lista.
watch(
  () => watcher.state.value,
  (state) => {
    if (state === 'found') emit('changed')
  },
)

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
    <Alert v-if="!canManage" tone="info">
      Generar y revocar tokens es tarea de Soporte. Aquí puedes ver los que ya existen.
    </Alert>

    <Card
      v-else
      title="Vincular una instalación"
      description="El token se muestra una sola vez y sirve para una sola instalación."
    >
      <Stepper :steps="steps" :current="current" class="tokens__stepper" />

      <div v-if="current === 'generate'" class="tokens__create">
        <Select v-model="expiresHours" label="Vigencia" :options="DURATIONS" data-test="token-duration" />
        <Button :loading="creating" class="tokens__button" data-test="token-create" @click="createToken">
          <KeyRound :size="15" aria-hidden="true" />
          Generar token de vinculación
        </Button>
      </div>

      <div v-else-if="current === 'install'" class="tokens__step" data-test="link-step-install">
        <p>Copia el token de la ventana y pégalo en la instalación de SAVI.</p>
      </div>

      <div v-else-if="current === 'waiting'" class="tokens__step" data-test="link-step-waiting">
        <template v-if="watcher.state.value === 'timeout'">
          <Alert tone="warning">
            No se detectó ninguna conexión en 10 minutos. Revisa que la instalación tenga salida a
            internet y que el token no haya vencido.
          </Alert>
          <div class="tokens__actions">
            <Button variant="secondary" data-test="link-keep-waiting" @click="keepWaiting">
              Seguir esperando
            </Button>
            <Button variant="ghost" data-test="link-another" @click="generateAnother">
              Generar otro token
            </Button>
          </div>
        </template>
        <template v-else>
          <p class="tokens__waiting" role="status">
            <Loader :size="15" class="tokens__spin" aria-hidden="true" />
            Esperando a que la instalación se conecte. Esta pantalla se actualiza sola.
          </p>
          <ol class="tokens__howto">
            <li>Instala SAVI en el equipo o servidor del cliente.</li>
            <li>
              En SAVI → Administración → SAVI Cloud, o en el instalador, pega el token y confirma
              la dirección de SAVI Cloud.
            </li>
          </ol>
          <div class="tokens__actions">
            <Button variant="ghost" data-test="link-another" @click="generateAnother">
              Generar otro token
            </Button>
          </div>
        </template>
      </div>

      <div v-else class="tokens__step" data-test="link-step-linked">
        <Alert tone="success">
          Instalación vinculada:
          <RouterLink
            v-if="watcher.found.value"
            :to="`/instancias/${watcher.found.value.id}`"
            data-test="link-instance"
          >
            {{ watcher.found.value.name }}
          </RouterLink>
        </Alert>
        <div class="tokens__actions">
          <Button variant="secondary" data-test="link-another" @click="generateAnother">
            Vincular otra instalación
          </Button>
        </div>
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
            v-if="canManage && row.state === 'pending'"
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
    instructions="Pégalo en SAVI → Administración → SAVI Cloud, o en el instalador."
    @close="closeToken"
  >
    <CopyField :value="cloudUrl" label="Dirección de SAVI Cloud" hint="La que usa el instalador (-SaviCloudUrl)." />
  </SecretDialog>

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

.tokens__stepper {
  margin-bottom: var(--space-5);
}

.tokens__step {
  display: grid;
  gap: var(--space-4);
}

.tokens__step p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.tokens__waiting {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.tokens__spin {
  animation: tokens-spin 1.2s linear infinite;
}

.tokens__howto {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding-left: var(--space-5);
  font-size: 12.5px;
  color: var(--text-muted);
}

.tokens__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

@keyframes tokens-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .tokens__spin {
    animation: none;
  }
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
