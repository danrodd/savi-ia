<script setup lang="ts">
import {
  Alert,
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  PageHeader,
  Skeleton,
  type TableColumn,
  toast,
} from '@savi/ui'
import { ArrowLeft, Ban, Pause, Play, RefreshCw, ShieldCheck, Users } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime, instanceState, reasonLabel, relativeTime } from '@/lib/format'
import type { Heartbeat } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

type Action = 'suspend' | 'activate' | 'confirm-fingerprint' | 'request-rotation' | 'revoke'

const route = useRoute()
const auth = useAuthStore()
const id = computed(() => String(route.params.id))

const instance = useAsync(() => consoleApi.instance(id.value))
const people = useAsync(() => consoleApi.instancePeople(id.value))
const technical = computed(() => auth.can('instances.read_technical'))

const history = ref<Heartbeat[]>([])
const nextCursor = ref<string | null>(null)
const historyError = ref<string | null>(null)
const historyLoading = ref(false)

async function loadHistory(more = false): Promise<void> {
  if (!technical.value) return
  historyLoading.value = true
  historyError.value = null
  try {
    const page = await consoleApi.heartbeats(
      id.value,
      more ? (nextCursor.value ?? undefined) : undefined,
    )
    history.value = more ? [...history.value, ...page.items] : page.items
    nextCursor.value = page.next_cursor
  } catch (e) {
    historyError.value = errorMessage(e)
  } finally {
    historyLoading.value = false
  }
}
void loadHistory()

watch(id, () => {
  void instance.reload()
  void people.reload()
  void loadHistory()
})

interface HeartbeatView {
  llm: { provider?: string; model?: string; usable?: boolean } | null
  erp: { total?: number; usable?: number; credentials_unreadable?: number } | null
  sessions: number | null
  warnings: string[]
  streams: { name: string; mark: string }[]
  lastError: string | null
}

const readable = computed<HeartbeatView | null>(() => {
  const hb = instance.data.value?.last_heartbeat ?? null
  if (!hb) return null
  const sync = (hb.sync ?? {}) as {
    streams?: Record<string, { watermark_at?: string }>
    last_error?: string | null
  }
  return {
    llm: (hb.llm as HeartbeatView['llm']) ?? null,
    erp: (hb.erp_databases as HeartbeatView['erp']) ?? null,
    sessions: typeof hb.active_sessions === 'number' ? hb.active_sessions : null,
    warnings: Array.isArray(hb.warnings) ? (hb.warnings as string[]) : [],
    streams: Object.entries(sync.streams ?? {}).map(([name, info]) => ({
      name,
      mark: formatDateTime(info.watermark_at),
    })),
    lastError: sync.last_error ?? null,
  }
})

const facts = computed(() => {
  const i = instance.data.value
  if (!i) return []
  const list: { label: string; value: string; mono?: boolean }[] = [
    { label: 'Versión', value: i.version ?? '—', mono: true },
    { label: 'Commit', value: i.commit ?? '—', mono: true },
    { label: 'Modo', value: i.deployment_mode },
    { label: 'Sistema', value: i.os },
    { label: 'Base del agente', value: i.agent_db_engine },
    { label: 'Vinculada', value: formatDateTime(i.enrolled_at) },
    { label: 'Último contacto', value: relativeTime(i.last_seen_at) },
  ]
  if (technical.value) {
    list.push({ label: 'Motivo del estado', value: reasonLabel(i.status_reason) })
    if (i.clock_skew_seconds !== null) {
      list.push({ label: 'Desfase de reloj', value: `${i.clock_skew_seconds} s` })
    }
    if (i.rotation_requested_at) {
      list.push({ label: 'Renovación pedida', value: relativeTime(i.rotation_requested_at) })
    }
  }
  return list
})

const PEOPLE_COLUMNS: TableColumn[] = [
  { key: 'user_ref', label: 'Persona' },
  { key: 'sessions', label: 'Sesiones', align: 'right', width: '110px' },
  { key: 'last_session_at', label: 'Última vez', width: '160px' },
]

const HISTORY_COLUMNS: TableColumn[] = [
  { key: 'received_at', label: 'Recibido', width: '170px' },
  { key: 'version', label: 'Versión', width: '120px', mono: true },
  { key: 'sessions', label: 'Sesiones', align: 'right', width: '100px' },
  { key: 'warnings', label: 'Avisos' },
]

const pending = ref<Action | null>(null)
const busy = ref(false)

const COPY: Record<
  Action,
  { title: string; message: string; confirm: string; danger: boolean; done: string }
> = {
  suspend: {
    title: 'Suspender instancia',
    message: 'Sigue hablando con Cloud, pero deja de guardarse lo que envía.',
    confirm: 'Suspender',
    danger: true,
    done: 'Instancia suspendida',
  },
  activate: {
    title: 'Reactivar instancia',
    message: 'Vuelve a guardar lo que envía. Retoma desde donde quedó, sin pérdida.',
    confirm: 'Reactivar',
    danger: false,
    done: 'Instancia reactivada',
  },
  'confirm-fingerprint': {
    title: 'Es la misma máquina',
    message: 'Se acepta la huella nueva y la instancia vuelve a estar activa.',
    confirm: 'Confirmar',
    danger: false,
    done: 'Huella confirmada',
  },
  'request-rotation': {
    title: 'Pedir renovación de credenciales',
    message: 'En su próximo contacto la instancia genera un secreto nuevo.',
    confirm: 'Pedir renovación',
    danger: false,
    done: 'Renovación pedida',
  },
  revoke: {
    title: 'Revocar instancia',
    message:
      'Es definitivo: la instancia deja de enviar métricas y tendrá que vincularse con un token nuevo.',
    confirm: 'Revocar',
    danger: true,
    done: 'Instancia revocada',
  },
}

async function run(): Promise<void> {
  const action = pending.value
  if (!action) return
  busy.value = true
  try {
    if (action === 'revoke') await consoleApi.revokeInstance(id.value, 'REVOCAR')
    else await consoleApi.instanceAction(id.value, action)
    toast.success(COPY[action].done)
    await instance.reload()
    await loadHistory()
  } catch (e) {
    toast.error('No se pudo completar la acción', { description: errorMessage(e) })
  } finally {
    busy.value = false
    pending.value = null
  }
}
</script>

<template>
  <div>
    <RouterLink to="/instancias" class="back">
      <ArrowLeft :size="14" aria-hidden="true" /> Instancias
    </RouterLink>

    <Alert v-if="instance.error.value" tone="danger">
      {{ instance.error.value }}
      <template #action>
        <Button size="sm" variant="secondary" @click="instance.reload()">Reintentar</Button>
      </template>
    </Alert>

    <div v-if="instance.loading.value && !instance.data.value" class="loading">
      <Skeleton height="30px" width="40%" />
      <Skeleton height="16px" width="25%" />
    </div>

    <template v-if="instance.data.value">
      <PageHeader :title="instance.data.value.name">
        <template #badges>
          <StatusBadge
            :tone="instanceState(instance.data.value).tone"
            :label="instanceState(instance.data.value).label"
          />
          <Badge v-if="instance.data.value.outdated" tone="warning">Desactualizada</Badge>
        </template>
        <template #meta>
          <RouterLink :to="`/clientes/${instance.data.value.client_id}`">
            {{ instance.data.value.client_name }}
          </RouterLink>
          <span>Último contacto {{ relativeTime(instance.data.value.last_seen_at) }}</span>
        </template>
        <template
          v-if="auth.can('instances.manage') && instance.data.value.status !== 'revoked'"
          #actions
        >
          <Button
            v-if="instance.data.value.status === 'active'"
            variant="secondary"
            @click="pending = 'suspend'"
          >
            <Pause :size="14" aria-hidden="true" /> Suspender
          </Button>
          <Button v-else variant="secondary" @click="pending = 'activate'">
            <Play :size="14" aria-hidden="true" /> Reactivar
          </Button>
          <Button variant="secondary" @click="pending = 'request-rotation'">
            <RefreshCw :size="14" aria-hidden="true" /> Renovar credenciales
          </Button>
          <Button variant="danger" @click="pending = 'revoke'">
            <Ban :size="14" aria-hidden="true" /> Revocar
          </Button>
        </template>
      </PageHeader>

      <div class="stack">
        <Alert
          v-if="instance.data.value.status_reason === 'fingerprint_mismatch'"
          tone="warning"
          title="La huella de la máquina cambió"
        >
          Puede ser una copia de la instalación o un cambio de hardware. Si es la misma máquina,
          confírmelo para reactivarla.
          <template v-if="auth.can('instances.manage')" #action>
            <Button size="sm" @click="pending = 'confirm-fingerprint'">
              <ShieldCheck :size="14" aria-hidden="true" /> Es la misma máquina
            </Button>
          </template>
        </Alert>

        <Card title="Datos de la instalación">
          <dl class="facts">
            <div v-for="fact in facts" :key="fact.label">
              <dt>{{ fact.label }}</dt>
              <dd :class="{ mono: fact.mono }">{{ fact.value }}</dd>
            </div>
          </dl>
        </Card>

        <Card title="Personas que usan esta instalación" padding="none" data-test="instance-people">
          <DataTable
            :columns="PEOPLE_COLUMNS"
            :rows="people.data.value ?? []"
            row-key="user_ref"
            :loading="people.loading.value"
          >
            <template #empty>
              <EmptyState :icon="Users" title="Todavía nadie inició sesión en esta instalación" />
            </template>
            <template #cell-user_ref="{ row }">
              <strong v-if="row.label">{{ row.label }}</strong>
              <code v-else>{{ row.user_ref.slice(0, 8) }}…</code>
            </template>
            <template #cell-last_session_at="{ row }">{{ relativeTime(row.last_session_at) }}</template>
          </DataTable>
        </Card>

        <Card v-if="technical && readable" title="Último heartbeat">
          <dl class="facts">
            <div v-if="readable.llm">
              <dt>Proveedor de IA</dt>
              <dd>
                {{ readable.llm.provider ?? '—' }} · {{ readable.llm.model ?? '—' }}
                <StatusBadge
                  :tone="readable.llm.usable ? 'ok' : 'bad'"
                  :label="readable.llm.usable ? 'Usable' : 'No usable'"
                />
              </dd>
            </div>
            <div v-if="readable.erp">
              <dt>Bases del ERP</dt>
              <dd>
                {{ readable.erp.usable ?? 0 }} de {{ readable.erp.total ?? 0 }} usables
                <span v-if="readable.erp.credentials_unreadable" class="muted">
                  · {{ readable.erp.credentials_unreadable }} con credenciales ilegibles
                </span>
              </dd>
            </div>
            <div v-if="readable.sessions !== null">
              <dt>Sesiones activas</dt>
              <dd>{{ readable.sessions }}</dd>
            </div>
          </dl>
          <Alert v-if="readable.lastError" tone="danger" title="Último error de envío" class="spaced">
            {{ readable.lastError }}
          </Alert>
          <div v-if="readable.warnings.length" class="warnings">
            <Badge v-for="w in readable.warnings" :key="w" tone="warning">{{ w }}</Badge>
          </div>
          <div v-if="readable.streams.length" class="streams">
            <p class="streams__title">Envíos</p>
            <ul>
              <li v-for="stream in readable.streams" :key="stream.name">
                <code>{{ stream.name }}</code> hasta {{ stream.mark }}
              </li>
            </ul>
          </div>
        </Card>

        <Card v-if="technical" title="Historial de contactos" padding="none">
          <Alert v-if="historyError" tone="danger" class="history-error">{{ historyError }}</Alert>
          <DataTable
            :columns="HISTORY_COLUMNS"
            :rows="history"
            row-key="id"
            :loading="historyLoading"
            empty-text="Sin contactos registrados."
          >
            <template #cell-received_at="{ row }">{{ formatDateTime(row.received_at) }}</template>
            <template #cell-version="{ row }">
              {{ (row.payload.version as string | undefined) ?? '—' }}
            </template>
            <template #cell-sessions="{ row }">
              {{ (row.payload.active_sessions as number | undefined) ?? '—' }}
            </template>
            <template #cell-warnings="{ row }">
              {{
                Array.isArray(row.payload.warnings) && row.payload.warnings.length
                  ? (row.payload.warnings as string[]).join(', ')
                  : '—'
              }}
            </template>
          </DataTable>
          <template v-if="nextCursor" #footer>
            <Button variant="secondary" :loading="historyLoading" @click="loadHistory(true)">
              Ver más
            </Button>
          </template>
        </Card>
      </div>
    </template>

    <ConfirmDialog
      :open="pending !== null"
      :title="pending ? COPY[pending].title : ''"
      :message="pending ? COPY[pending].message : ''"
      :confirm-label="pending ? COPY[pending].confirm : 'Confirmar'"
      :danger="pending ? COPY[pending].danger : false"
      :type-to-confirm="pending === 'revoke' ? 'REVOCAR' : undefined"
      :busy="busy"
      @confirm="run"
      @cancel="pending = null"
    />
  </div>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 32px;
  margin-bottom: var(--space-4);
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}

.back:hover {
  color: var(--text);
  text-decoration: none;
}

.loading {
  display: grid;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-5) var(--space-6);
  margin: 0;
}

.facts dt {
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.facts dd {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-1) 0 0;
  font-size: 13.5px;
  overflow-wrap: anywhere;
}

.facts dd.mono {
  font-family: var(--font-mono);
  font-size: 12.5px;
}

.spaced {
  margin-top: var(--space-5);
}

.warnings {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-5);
}

.streams {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border);
  font-size: 13px;
}

.streams__title {
  margin: 0 0 var(--space-2);
  font-weight: var(--fw-semibold);
}

.streams ul {
  margin: 0;
  padding-left: var(--space-6);
  color: var(--text-muted);
}

.history-error {
  margin: var(--space-4);
}
</style>
