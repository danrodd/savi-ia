<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime, instanceStatusLabel, reasonLabel, relativeTime } from '@/lib/format'
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

async function loadHistory(more = false): Promise<void> {
  if (!technical.value) return
  try {
    const page = await consoleApi.heartbeats(
      id.value,
      more ? (nextCursor.value ?? undefined) : undefined,
    )
    history.value = more ? [...history.value, ...page.items] : page.items
    nextCursor.value = page.next_cursor
  } catch (e) {
    historyError.value = errorMessage(e)
  }
}
void loadHistory()

const heartbeat = computed(() => instance.data.value?.last_heartbeat ?? null)

interface HeartbeatView {
  llm: { provider?: string; model?: string; usable?: boolean } | null
  erp: { total?: number; usable?: number; credentials_unreadable?: number } | null
  sessions: number | null
  warnings: string[]
  streams: [string, string][]
  lastError: string | null
}

const readable = computed<HeartbeatView | null>(() => {
  const hb = heartbeat.value
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
    streams: Object.entries(sync.streams ?? {}).map(
      ([name, info]) => [name, formatDateTime(info.watermark_at)] as [string, string],
    ),
    lastError: sync.last_error ?? null,
  }
})

const pending = ref<Action | null>(null)
const busy = ref(false)
const actionError = ref<string | null>(null)

const COPY: Record<Action, { title: string; message: string; confirm: string; danger: boolean }> = {
  suspend: {
    title: 'Suspender instancia',
    message: 'Sigue hablando con Cloud, pero deja de guardarse lo que envía.',
    confirm: 'Suspender',
    danger: true,
  },
  activate: {
    title: 'Reactivar instancia',
    message: 'Vuelve a guardar lo que envía. Retoma desde donde quedó, sin pérdida.',
    confirm: 'Reactivar',
    danger: false,
  },
  'confirm-fingerprint': {
    title: 'Es la misma máquina',
    message: 'Se acepta la huella nueva y la instancia vuelve a estar activa.',
    confirm: 'Confirmar',
    danger: false,
  },
  'request-rotation': {
    title: 'Pedir renovación de credenciales',
    message: 'En su próximo contacto la instancia genera un secreto nuevo.',
    confirm: 'Pedir renovación',
    danger: false,
  },
  revoke: {
    title: 'Revocar instancia',
    message:
      'Es definitivo: la instancia deja de enviar métricas y tendrá que vincularse con un token nuevo.',
    confirm: 'Revocar',
    danger: true,
  },
}

async function run(): Promise<void> {
  const action = pending.value
  if (!action) return
  busy.value = true
  actionError.value = null
  try {
    if (action === 'revoke') await consoleApi.revokeInstance(id.value, 'REVOCAR')
    else await consoleApi.instanceAction(id.value, action)
    await instance.reload()
    await loadHistory()
  } catch (e) {
    actionError.value = errorMessage(e)
  } finally {
    busy.value = false
    pending.value = null
  }
}
</script>

<template>
  <div class="stack">
    <p><RouterLink to="/instancias">← Instancias</RouterLink></p>
    <p v-if="instance.error.value" class="error-text" role="alert">{{ instance.error.value }}</p>

    <template v-if="instance.data.value">
      <div class="spread">
        <div>
          <h1>{{ instance.data.value.name }}</h1>
          <p class="muted">
            <RouterLink :to="`/clientes/${instance.data.value.client_id}`">
              {{ instance.data.value.client_name }}
            </RouterLink>
          </p>
        </div>
        <StatusBadge
          :tone="
            instance.data.value.status === 'active'
              ? instance.data.value.online
                ? 'ok'
                : 'warn'
              : 'bad'
          "
          :label="
            instance.data.value.status === 'active'
              ? instance.data.value.online
                ? 'En línea'
                : 'Sin conexión'
              : instanceStatusLabel(instance.data.value.status)
          "
        />
      </div>

      <p v-if="actionError" class="error-text" role="alert">{{ actionError }}</p>

      <div v-if="auth.can('instances.manage') && instance.data.value.status !== 'revoked'" class="row">
        <button
          v-if="instance.data.value.status === 'active'"
          class="btn"
          type="button"
          @click="pending = 'suspend'"
        >
          Suspender
        </button>
        <button v-else class="btn" type="button" @click="pending = 'activate'">Reactivar</button>
        <button
          v-if="instance.data.value.status_reason === 'fingerprint_mismatch'"
          class="btn btn-primary"
          type="button"
          @click="pending = 'confirm-fingerprint'"
        >
          Es la misma máquina
        </button>
        <button class="btn" type="button" @click="pending = 'request-rotation'">
          Pedir renovación de credenciales
        </button>
        <button class="btn btn-danger" type="button" @click="pending = 'revoke'">Revocar</button>
      </div>

      <section class="card facts">
        <div><span class="muted">Versión</span> {{ instance.data.value.version ?? '—' }}</div>
        <div><span class="muted">Commit</span> {{ instance.data.value.commit ?? '—' }}</div>
        <div><span class="muted">Modo</span> {{ instance.data.value.deployment_mode }}</div>
        <div><span class="muted">Sistema</span> {{ instance.data.value.os }}</div>
        <div><span class="muted">Base del agente</span> {{ instance.data.value.agent_db_engine }}</div>
        <div><span class="muted">Vinculada</span> {{ formatDateTime(instance.data.value.enrolled_at) }}</div>
        <div>
          <span class="muted">Último contacto</span>
          {{ relativeTime(instance.data.value.last_seen_at) }}
        </div>
        <div v-if="technical">
          <span class="muted">Motivo del estado</span>
          {{ reasonLabel(instance.data.value.status_reason) }}
        </div>
        <div v-if="technical && instance.data.value.clock_skew_seconds !== null">
          <span class="muted">Desfase de reloj</span>
          {{ instance.data.value.clock_skew_seconds }} s
        </div>
        <div v-if="technical && instance.data.value.rotation_requested_at">
          <span class="muted">Renovación pedida</span>
          {{ relativeTime(instance.data.value.rotation_requested_at) }}
        </div>
      </section>

      <section class="card stack" data-test="instance-people">
        <h2>Personas que usan esta instalación</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Persona</th>
                <th class="num">Sesiones</th>
                <th>Última vez</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in people.data.value ?? []" :key="p.user_ref">
                <td>
                  <strong v-if="p.label">{{ p.label }}</strong>
                  <code v-else>{{ p.user_ref.slice(0, 8) }}…</code>
                </td>
                <td class="num">{{ p.sessions }}</td>
                <td>{{ relativeTime(p.last_session_at) }}</td>
              </tr>
              <tr v-if="!people.loading.value && !(people.data.value?.length ?? 0)">
                <td colspan="3" class="empty">Todavía nadie inició sesión en esta instalación.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="technical && readable" class="card stack">
        <h2>Último heartbeat</h2>
        <div class="facts">
          <div v-if="readable.llm">
            <span class="muted">Proveedor de IA</span>
            {{ readable.llm.provider ?? '—' }} · {{ readable.llm.model ?? '—' }}
            <StatusBadge
              :tone="readable.llm.usable ? 'ok' : 'bad'"
              :label="readable.llm.usable ? 'Usable' : 'No usable'"
            />
          </div>
          <div v-if="readable.erp">
            <span class="muted">Bases del ERP</span>
            {{ readable.erp.usable ?? 0 }} de {{ readable.erp.total ?? 0 }} usables
            <span v-if="readable.erp.credentials_unreadable">
              · {{ readable.erp.credentials_unreadable }} con credenciales ilegibles
            </span>
          </div>
          <div v-if="readable.sessions !== null">
            <span class="muted">Sesiones activas</span> {{ readable.sessions }}
          </div>
          <div v-if="readable.lastError">
            <span class="muted">Último error de envío</span>
            <StatusBadge tone="bad" :label="readable.lastError" />
          </div>
        </div>
        <div v-if="readable.warnings.length" class="row">
          <StatusBadge v-for="w in readable.warnings" :key="w" tone="warn" :label="w" />
        </div>
        <div v-if="readable.streams.length">
          <h2>Envíos</h2>
          <ul class="streams">
            <li v-for="[name, mark] in readable.streams" :key="name">
              <code>{{ name }}</code> hasta {{ mark }}
            </li>
          </ul>
        </div>
      </section>

      <section v-if="technical" class="stack">
        <h2>Historial de contactos</h2>
        <p v-if="historyError" class="error-text" role="alert">{{ historyError }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Recibido</th>
                <th>Versión</th>
                <th>Sesiones</th>
                <th>Avisos</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in history" :key="h.id">
                <td>{{ formatDateTime(h.received_at) }}</td>
                <td>{{ (h.payload.version as string | undefined) ?? '—' }}</td>
                <td>{{ (h.payload.active_sessions as number | undefined) ?? '—' }}</td>
                <td>
                  {{
                    Array.isArray(h.payload.warnings) && h.payload.warnings.length
                      ? (h.payload.warnings as string[]).join(', ')
                      : '—'
                  }}
                </td>
              </tr>
              <tr v-if="!history.length">
                <td colspan="4" class="empty">Sin contactos registrados.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <button v-if="nextCursor" class="btn" type="button" @click="loadHistory(true)">
          Ver más
        </button>
      </section>
    </template>

    <ConfirmDialog
      v-if="pending"
      :open="true"
      :title="COPY[pending].title"
      :message="COPY[pending].message"
      :confirm-label="COPY[pending].confirm"
      :danger="COPY[pending].danger"
      :type-to-confirm="pending === 'revoke' ? 'REVOCAR' : undefined"
      :busy="busy"
      @confirm="run"
      @cancel="pending = null"
    />
  </div>
</template>

<style scoped>
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0.6rem 1.2rem;
}
.facts .muted {
  display: block;
  font-size: 0.78rem;
}
.streams {
  margin: 0;
  padding-left: 1.1rem;
}
</style>
