<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccessPolicyCard from '@/components/AccessPolicyCard.vue'
import AiPolicyCard from '@/components/AiPolicyCard.vue'
import BarChart from '@/components/BarChart.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import KpiCard from '@/components/KpiCard.vue'
import SecretDialog from '@/components/SecretDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import {
  formatDateTime,
  formatDay,
  formatInt,
  formatMs,
  formatPercent,
  formatUsd,
  instanceStatusLabel,
  relativeTime,
} from '@/lib/format'
import type { Severity } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

type Tab = 'usage' | 'databases' | 'users' | 'instances' | 'tokens' | 'alerts'

const route = useRoute()
const auth = useAuthStore()
const id = computed(() => String(route.params.id))
const tab = ref<Tab>('usage')

const client = useAsync(() => consoleApi.client(id.value))
const metrics = useAsync(() => consoleApi.clientMetrics(id.value))
const databases = useAsync(() => consoleApi.clientDatabases(id.value), false)
const users = useAsync(() => consoleApi.clientUsers(id.value), false)
const instances = useAsync(() => consoleApi.instances({ client_id: id.value }), false)
const tokens = useAsync(
  () => (auth.can('tokens.manage') ? consoleApi.tokens(id.value) : Promise.resolve([])),
  false,
)
const alerts = useAsync(() => consoleApi.alerts({ client_id: id.value }), false)

const loaders: Record<Tab, () => Promise<void>> = {
  usage: async () => undefined,
  databases: () => databases.reload(),
  users: () => users.reload(),
  instances: () => instances.reload(),
  tokens: () => tokens.reload(),
  alerts: () => alerts.reload(),
}

function selectTab(next: Tab): void {
  tab.value = next
  void loaders[next]()
}

const tabs = computed<{ key: Tab; label: string }[]>(() => {
  const all: { key: Tab; label: string }[] = [
    { key: 'usage', label: 'Uso' },
    { key: 'databases', label: 'Sucursales' },
    { key: 'users', label: 'Usuarios' },
    { key: 'instances', label: 'Instancias' },
  ]
  if (auth.can('tokens.manage')) all.push({ key: 'tokens', label: 'Vinculación' })
  all.push({ key: 'alerts', label: 'Alertas' })
  return all
})

const series = computed(() =>
  (metrics.data.value?.series ?? []).map((d) => ({
    label: formatDay(d.day).slice(0, 5),
    value: d.turns,
  })),
)

const SEVERITY_TONE: Record<Severity, 'muted' | 'warn' | 'bad'> = {
  info: 'muted',
  warning: 'warn',
  critical: 'bad',
}

// --- acciones sobre el cliente
const action = ref<'suspend' | 'activate' | null>(null)
const actionBusy = ref(false)
const actionError = ref<string | null>(null)

async function runClientAction(): Promise<void> {
  if (!action.value) return
  actionBusy.value = true
  actionError.value = null
  try {
    if (action.value === 'suspend') await consoleApi.suspendClient(id.value)
    else await consoleApi.activateClient(id.value)
    action.value = null
    await client.reload()
    await instances.reload()
  } catch (e) {
    actionError.value = errorMessage(e)
    action.value = null
  } finally {
    actionBusy.value = false
  }
}

// --- política de las instalaciones del cliente
type PolicyChange = 'lock' | 'unlock' | 'named' | 'pseudonym' | 'cli_on' | 'cli_off'
const policyChange = ref<PolicyChange | null>(null)
const policyBusy = ref(false)
const policyError = ref<string | null>(null)

const POLICY_COPY: Record<PolicyChange, { title: string; message: string; confirm: string }> = {
  lock: {
    title: 'Dejar las instalaciones solo con el chat',
    message:
      'En cada equipo de este cliente se oculta Administración y se rechaza cualquier cambio de configuración. Aplica en el próximo contacto de cada instalación.',
    confirm: 'Bloquear configuración',
  },
  unlock: {
    title: 'Permitir configurar las instalaciones',
    message:
      'Las personas administradoras de cada equipo vuelven a ver Administración. Aplica en el próximo contacto.',
    confirm: 'Permitir configuración',
  },
  named: {
    title: 'Identificar a las personas por su usuario',
    message:
      'Cloud va a guardar el código de usuario de quienes inician sesión (por ejemplo JPEREZ), no solo un seudónimo. Corresponde a la organización interna: no lo actives para un cliente que no lo autorizó.',
    confirm: 'Identificar personas',
  },
  cli_on: {
    title: 'Permitir el CLI de Claude en las instalaciones',
    message:
      'Quien administre una instalación local podrá usar la sesión de Claude iniciada en su equipo, con su propia cuenta. El consumo de esa cuenta no pasa por SEO Group. Aplica en el próximo contacto.',
    confirm: 'Permitir CLI de Claude',
  },
  cli_off: {
    title: 'Dejar de permitir el CLI de Claude',
    message:
      'Las instalaciones que lo estén usando dejan de responder en el turno siguiente hasta que se configure otro proveedor de IA.',
    confirm: 'No permitir',
  },
  pseudonym: {
    title: 'Volver a seudónimos',
    message:
      'Las instalaciones dejan de enviar el código de usuario. Los ya guardados se conservan hasta que venzan.',
    confirm: 'Usar seudónimos',
  },
}

async function applyPolicy(): Promise<void> {
  const change = policyChange.value
  if (!change) return
  policyBusy.value = true
  policyError.value = null
  try {
    await consoleApi.setClientPolicy(
      id.value,
      change === 'lock' || change === 'unlock'
        ? { config_locked: change === 'lock' }
        : change === 'cli_on' || change === 'cli_off'
          ? { allow_local_cli: change === 'cli_on' }
          : { identity_mode: change },
    )
    await client.reload()
  } catch (e) {
    policyError.value = errorMessage(e)
  } finally {
    policyBusy.value = false
    policyChange.value = null
  }
}

// --- tokens de vinculación
const expiresHours = ref(72)
const createdToken = ref<string | null>(null)
const tokenError = ref<string | null>(null)

async function createToken(): Promise<void> {
  tokenError.value = null
  try {
    const created = await consoleApi.createToken(id.value, expiresHours.value)
    createdToken.value = created.token
  } catch (e) {
    tokenError.value = errorMessage(e)
  }
}

async function closeToken(): Promise<void> {
  // El token ya no se puede recuperar: se descarta de memoria al cerrar.
  createdToken.value = null
  await tokens.reload()
}

async function revokeToken(tokenId: string): Promise<void> {
  try {
    await consoleApi.revokeToken(tokenId)
    await tokens.reload()
  } catch (e) {
    tokenError.value = errorMessage(e)
  }
}

const TOKEN_STATE: Record<string, { label: string; tone: 'ok' | 'muted' | 'warn' | 'bad' }> = {
  pending: { label: 'Vigente', tone: 'ok' },
  used: { label: 'Usado', tone: 'muted' },
  expired: { label: 'Vencido', tone: 'warn' },
  revoked: { label: 'Revocado', tone: 'bad' },
}
</script>

<template>
  <div class="stack">
    <p><RouterLink to="/clientes">← Clientes</RouterLink></p>
    <p v-if="client.error.value" class="error-text" role="alert">{{ client.error.value }}</p>

    <template v-if="client.data.value">
      <div class="spread">
        <div>
          <h1>{{ client.data.value.name }}</h1>
          <p class="muted">
            <code>{{ client.data.value.code }}</code>
            <span v-if="client.data.value.nit"> · NIT {{ client.data.value.nit }}</span>
          </p>
        </div>
        <div class="row">
          <FreshnessChip v-if="metrics.data.value" :seconds="metrics.data.value.freshness.seconds" />
          <StatusBadge
            :tone="client.data.value.status === 'active' ? 'ok' : 'bad'"
            :label="client.data.value.status === 'active' ? 'Activo' : 'Suspendido'"
          />
          <template v-if="auth.can('clients.suspend')">
            <button
              v-if="client.data.value.status === 'active'"
              class="btn btn-danger btn-small"
              type="button"
              @click="action = 'suspend'"
            >
              Suspender cliente
            </button>
            <button v-else class="btn btn-small" type="button" @click="action = 'activate'">
              Reactivar cliente
            </button>
          </template>
        </div>
      </div>
      <p v-if="actionError" class="error-text" role="alert">{{ actionError }}</p>

      <section v-if="auth.can('clients.policy')" class="card policy" data-test="client-policy">
        <h2>Política de las instalaciones</h2>
        <p v-if="policyError" class="error-text" role="alert">{{ policyError }}</p>
        <div class="policy__row">
          <div>
            <strong>Configuración</strong>
            <p class="muted">
              {{
                client.data.value.config_locked
                  ? 'Bloqueada: cada equipo queda solo con el chat.'
                  : 'Libre: las personas administradoras de cada equipo pueden configurar.'
              }}
            </p>
          </div>
          <button
            class="btn btn-small"
            type="button"
            data-test="toggle-lock"
            @click="policyChange = client.data.value.config_locked ? 'unlock' : 'lock'"
          >
            {{ client.data.value.config_locked ? 'Permitir configuración' : 'Bloquear configuración' }}
          </button>
        </div>
        <div class="policy__row">
          <div>
            <strong>Identidad de las personas</strong>
            <p class="muted">
              {{
                client.data.value.identity_mode === 'named'
                  ? 'Por código de usuario (organización interna).'
                  : 'Por seudónimo: Cloud no sabe quiénes son.'
              }}
            </p>
          </div>
          <button
            class="btn btn-small"
            type="button"
            data-test="toggle-identity"
            @click="policyChange = client.data.value.identity_mode === 'named' ? 'pseudonym' : 'named'"
          >
            {{ client.data.value.identity_mode === 'named' ? 'Usar seudónimos' : 'Identificar personas' }}
          </button>
        </div>
        <div class="policy__row">
          <div>
            <strong>CLI de Claude en el equipo</strong>
            <p class="muted">
              {{
                client.data.value.allow_local_cli
                  ? 'Permitido: la instalación local puede usar la sesión de Claude de la persona.'
                  : 'No permitido: solo se usan las claves que configure el administrador.'
              }}
            </p>
          </div>
          <button
            class="btn btn-small"
            type="button"
            data-test="toggle-cli"
            @click="policyChange = client.data.value.allow_local_cli ? 'cli_off' : 'cli_on'"
          >
            {{ client.data.value.allow_local_cli ? 'No permitir' : 'Permitir CLI de Claude' }}
          </button>
        </div>
      </section>

      <AiPolicyCard
        v-if="auth.can('clients.policy')"
        :client-id="id"
        :policy="client.data.value.ai_policy"
        @saved="client.reload()"
      />

      <AccessPolicyCard
        v-if="auth.can('clients.policy')"
        :client-id="id"
        :policy="client.data.value.access_policy"
        @saved="client.reload()"
      />

      <div class="tabs" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.key"
          role="tab"
          class="tab"
          :class="{ active: tab === t.key }"
          :aria-selected="tab === t.key"
          type="button"
          @click="selectTab(t.key)"
        >
          {{ t.label }}
        </button>
      </div>

      <!-- Uso -->
      <div v-if="tab === 'usage'" class="stack">
        <p v-if="metrics.error.value" class="error-text" role="alert">{{ metrics.error.value }}</p>
        <template v-if="metrics.data.value">
          <p class="muted">Últimos 30 días.</p>
          <div class="grid-kpi">
            <KpiCard label="Turnos" metric="turns" :value="formatInt(metrics.data.value.totals.turns)" />
            <KpiCard
              label="Usuarios activos"
              metric="active_users"
              :value="formatInt(metrics.data.value.totals.active_users)"
              :hint="`${metrics.data.value.totals.entering_users} entran`"
            />
            <KpiCard
              label="Adopción"
              metric="adoption"
              :value="formatPercent(metrics.data.value.totals.adoption)"
            />
            <KpiCard
              label="Costo"
              metric="cost_usd"
              :value="formatUsd(metrics.data.value.totals.cost_usd)"
              :hint="`${metrics.data.value.totals.turns_without_price} turnos sin precio`"
            />
            <KpiCard
              label="Tasa de error"
              metric="error_rate"
              :value="formatPercent(metrics.data.value.totals.error_rate)"
              :hint="`${metrics.data.value.totals.turns_with_error} con error`"
            />
            <KpiCard
              label="Latencia p50 / p90"
              metric="latency"
              :value="`${formatMs(metrics.data.value.totals.latency_p50_ms)} / ${formatMs(
                metrics.data.value.totals.latency_p90_ms,
              )}`"
            />
          </div>
          <section class="card">
            <h2>Turnos por día</h2>
            <BarChart :data="series" :format="formatInt" />
          </section>
          <h2>Por modelo</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Proveedor</th>
                  <th>Modelo</th>
                  <th class="num">Turnos</th>
                  <th class="num">Tokens</th>
                  <th class="num">Costo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in metrics.data.value.by_model" :key="`${m.provider}-${m.model}`">
                  <td>{{ m.provider ?? '—' }}</td>
                  <td>{{ m.model ?? '—' }}</td>
                  <td class="num">{{ formatInt(m.turns) }}</td>
                  <td class="num">{{ formatInt(m.tokens) }}</td>
                  <td class="num">{{ formatUsd(m.cost_usd) }}</td>
                </tr>
                <tr v-if="!metrics.data.value.by_model.length">
                  <td colspan="5" class="empty">Sin turnos en el período.</td>
                </tr>
              </tbody>
            </table>
          </div>
          <h2>Herramientas</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Herramienta</th>
                  <th>Tipo</th>
                  <th class="num">Usos</th>
                  <th class="num">Con error</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in metrics.data.value.tools" :key="`${t.name}-${t.tipo}`">
                  <td>{{ t.name }}</td>
                  <td>{{ t.tipo ?? '—' }}</td>
                  <td class="num">{{ formatInt(t.uses) }}</td>
                  <td class="num">{{ formatInt(t.errors) }}</td>
                </tr>
                <tr v-if="!metrics.data.value.tools.length">
                  <td colspan="4" class="empty">Sin uso de herramientas.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>

      <!-- Sucursales -->
      <div v-else-if="tab === 'databases'" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Sucursal</th>
              <th>Código</th>
              <th>Estado</th>
              <th>Última conexión</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in databases.data.value ?? []" :key="d.database_ref">
              <td>{{ d.name }}</td>
              <td>
                <code>{{ d.code }}</code>
              </td>
              <td>
                <StatusBadge
                  v-if="d.credentials_unreadable"
                  tone="bad"
                  label="Credenciales ilegibles"
                />
                <StatusBadge v-else-if="!d.is_active" tone="muted" label="Inactiva" />
                <StatusBadge v-else-if="!d.is_usable" tone="warn" label="Sin conexión" />
                <StatusBadge v-else tone="ok" label="En uso" />
              </td>
              <td>{{ formatDateTime(d.last_connection_ok_at) }}</td>
            </tr>
            <tr v-if="!databases.loading.value && !(databases.data.value?.length ?? 0)">
              <td colspan="4" class="empty">Todavía no informaron sucursales.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Usuarios -->
      <div v-else-if="tab === 'users'" class="stack">
        <p class="muted">
          Los usuarios se identifican por un seudónimo: Cloud no recibe nombres ni correos.
        </p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Seudónimo</th>
                <th class="num">Turnos</th>
                <th class="num">Costo</th>
                <th class="num">Sucursales</th>
                <th>Último uso</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users.data.value ?? []" :key="u.user_ref">
                <td>
                  <strong v-if="u.label">{{ u.label }}</strong>
                  <code v-else>{{ u.user_ref.slice(0, 8) }}…</code>
                </td>
                <td class="num">{{ formatInt(u.turns) }}</td>
                <td class="num">{{ formatUsd(u.cost_usd) }}</td>
                <td class="num">{{ u.databases_used }}</td>
                <td>{{ relativeTime(u.last_used_at) }}</td>
              </tr>
              <tr v-if="!users.loading.value && !(users.data.value?.length ?? 0)">
                <td colspan="5" class="empty">Sin usuarios activos en el período.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Instancias -->
      <div v-else-if="tab === 'instances'" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Estado</th>
              <th>Versión</th>
              <th>Último contacto</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="i in instances.data.value ?? []" :key="i.id">
              <td>
                <RouterLink :to="`/instancias/${i.id}`">{{ i.name }}</RouterLink>
              </td>
              <td>
                <StatusBadge
                  :tone="i.status === 'active' ? (i.online ? 'ok' : 'warn') : 'bad'"
                  :label="
                    i.status === 'active'
                      ? i.online
                        ? 'En línea'
                        : 'Sin conexión'
                      : instanceStatusLabel(i.status)
                  "
                />
              </td>
              <td>{{ i.version ?? '—' }}</td>
              <td>{{ relativeTime(i.last_seen_at) }}</td>
            </tr>
            <tr v-if="!instances.loading.value && !(instances.data.value?.length ?? 0)">
              <td colspan="4" class="empty">
                Todavía no hay instancias vinculadas. Generá un token en «Vinculación».
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Vinculación -->
      <div v-else-if="tab === 'tokens'" class="stack">
        <div class="card row">
          <label class="hours">
            Vigencia del token (horas, hasta 168)
            <input v-model.number="expiresHours" type="number" min="1" max="168" />
          </label>
          <button class="btn btn-primary" type="button" @click="createToken">
            Generar token de vinculación
          </button>
        </div>
        <p v-if="tokenError" class="error-text" role="alert">{{ tokenError }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Estado</th>
                <th>Creado</th>
                <th>Vence</th>
                <th>Creado por</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in tokens.data.value ?? []" :key="t.id">
                <td>
                  <StatusBadge
                    :tone="TOKEN_STATE[t.state]?.tone ?? 'muted'"
                    :label="TOKEN_STATE[t.state]?.label ?? t.state"
                  />
                </td>
                <td>{{ formatDateTime(t.created_at) }}</td>
                <td>{{ formatDateTime(t.expires_at) }}</td>
                <td>{{ t.created_by }}</td>
                <td>
                  <button
                    v-if="t.state === 'pending'"
                    class="btn btn-small btn-danger"
                    type="button"
                    @click="revokeToken(t.id)"
                  >
                    Revocar
                  </button>
                </td>
              </tr>
              <tr v-if="!tokens.loading.value && !(tokens.data.value?.length ?? 0)">
                <td colspan="5" class="empty">Todavía no se generó ningún token.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Alertas -->
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Severidad</th>
              <th>Regla</th>
              <th>Estado</th>
              <th>Abierta</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in alerts.data.value ?? []" :key="a.id">
              <td><StatusBadge :tone="SEVERITY_TONE[a.severity]" :label="a.severity" /></td>
              <td>{{ a.rule_code }}</td>
              <td>{{ a.status }}</td>
              <td>{{ relativeTime(a.opened_at) }}</td>
            </tr>
            <tr v-if="!alerts.loading.value && !(alerts.data.value?.length ?? 0)">
              <td colspan="4" class="empty">Sin alertas para este cliente.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <ConfirmDialog
      :open="action !== null"
      :title="action === 'suspend' ? 'Suspender cliente' : 'Reactivar cliente'"
      :message="
        action === 'suspend'
          ? 'Se suspenden también todas sus instancias: dejan de enviar datos y no se pueden generar tokens nuevos.'
          : 'Se reactivan las instancias que se suspendieron junto con el cliente.'
      "
      :confirm-label="action === 'suspend' ? 'Suspender' : 'Reactivar'"
      :danger="action === 'suspend'"
      :busy="actionBusy"
      @confirm="runClientAction"
      @cancel="action = null"
    />
    <ConfirmDialog
      :open="policyChange !== null"
      :title="policyChange ? POLICY_COPY[policyChange].title : ''"
      :message="policyChange ? POLICY_COPY[policyChange].message : ''"
      :confirm-label="policyChange ? POLICY_COPY[policyChange].confirm : 'Confirmar'"
      :danger="policyChange === 'lock' || policyChange === 'named' || policyChange === 'cli_on'"
      :busy="policyBusy"
      @confirm="applyPolicy"
      @cancel="policyChange = null"
    />
    <SecretDialog
      :open="createdToken !== null"
      title="Token de vinculación"
      :secret="createdToken ?? ''"
      instructions="Pegalo en SAVI → Administración → SAVI Cloud, o en el instalador."
      @close="closeToken"
    />
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 0.2rem;
  overflow-x: auto;
  border-bottom: 1px solid var(--border);
}
.tab {
  padding: 0.5rem 0.9rem;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  white-space: nowrap;
}
.tab.active {
  color: var(--text);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
.hours {
  max-width: 280px;
}
.policy {
  display: grid;
  gap: 0.8rem;
}
.policy__row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
}
.policy__row p {
  margin: 0.15rem 0 0;
}
</style>
