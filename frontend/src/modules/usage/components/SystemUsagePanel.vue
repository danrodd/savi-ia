<script setup lang="ts">
/**
 * Panel "Global" (admin) — total del sistema + ranking de consumo por
 * usuario. Carga con guarda al activarse su tab.
 */
import { computed, onMounted } from 'vue'

import { useErpDatabaseStore } from '@/modules/admin/stores/erpDatabaseStore'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import { useUsageStore } from '../stores/usageStore'
import { buildDatabaseRows, databaseLabel } from '../utils/databases'
import { formatCop, formatTokens, formatUsd } from '../utils/format'
import ProviderBreakdown from './ProviderBreakdown.vue'
import ProviderDailyChart from './ProviderDailyChart.vue'

const store = useUsageStore()
const authStore = useAuthStore()
const databaseStore = useErpDatabaseStore()
const rate = computed(() => store.usdToCopRate)

// Por base CONSULTADA: cuánto costó atender a cada cliente. Un usuario de
// soporte atiende a varios desde una sola sesión.
// La lectura de documentos con IA viene aparte del chat (`totals` es solo
// el chat): el total del sistema los suma, y cada uno se ve por separado.
const documents = computed(() => store.system?.document_reading ?? null)
const chatCostUsd = computed(() => store.system?.totals.cost_usd ?? 0)
const totalCostUsd = computed(() => chatCostUsd.value + (documents.value?.cost_usd ?? 0))

const databaseRows = computed(() =>
  buildDatabaseRows(store.system?.per_database ?? [], databaseStore.databases),
)

// El id del ERP se repite entre clientes: sin la base, el usuario 1 de
// farmacias y el 1 de frami se ven como la misma persona.
function userLabel(userId: number | null, databaseId: string | null): string {
  if (userId === null) return 'Sin usuario (legado)'
  const base = databaseLabel(databaseId, databaseStore.databases)
  const me = authStore.user
  // Mismo id Y misma base de login: el id solo no alcanza, se repite entre
  // clientes (el `admin` de farmacias y el de sur_andina son el id 1).
  const isMe = userId === me?.id && databaseId === (me?.erp_database?.id ?? null)
  return `#${userId} · ${base}${isMe ? ' · vos' : ''}`
}

onMounted(() => {
  if (!store.system && !store.loadingSystem) void store.loadSystem()
  if (databaseStore.databases.length === 0 && !databaseStore.loading) void databaseStore.load()
})
</script>

<template>
  <section class="su" aria-label="Consumo global">
    <p v-if="store.loadingSystem && !store.system" class="su__hint">Cargando…</p>
    <p v-else-if="store.errorSystem" class="su__error" role="alert">
      {{ store.errorSystem }}
    </p>
    <template v-else-if="store.system">
      <div class="su__cards">
        <article class="su__card su__card--primary">
          <p class="su__card-label">Costo total del sistema</p>
          <p class="su__card-value">{{ formatCop(totalCostUsd, rate) }}</p>
          <p class="su__card-foot">{{ formatUsd(totalCostUsd) }} USD</p>
          <p v-if="documents && documents.requests > 0" class="su__card-foot">
            Chat {{ formatCop(chatCostUsd, rate) }} · Documentos
            {{ formatCop(documents.cost_usd, rate) }}
          </p>
          <!-- Sin esto, las respuestas de un modelo sin tarifa se suman como
               cero y el total parece completo cuando no lo es. -->
          <p v-if="store.system.totals.untariffed_count > 0" class="su__card-warning">
            {{ store.system.totals.untariffed_count }}
            {{ store.system.totals.untariffed_count === 1 ? 'respuesta' : 'respuestas' }}
            sin tarifa cargada: el costo real es mayor. Cargá los precios del modelo
            en Proveedores de IA.
          </p>
        </article>
        <article class="su__card">
          <p class="su__card-label">Tokens totales</p>
          <p class="su__card-value">{{ formatTokens(store.system.totals.total_tokens) }}</p>
          <p class="su__card-foot">
            {{ formatTokens(store.system.totals.message_count) }} respuestas
          </p>
        </article>
      </div>

      <section
        v-if="documents && documents.requests > 0"
        class="su__ranking"
        aria-label="Lectura de documentos con IA"
      >
        <h2 class="su__section-title">Lectura de documentos con IA</h2>
        <p v-if="documents.untariffed_count > 0" class="su__card-warning">
          {{ documents.untariffed_count }}
          {{ documents.untariffed_count === 1 ? 'lectura' : 'lecturas' }} sin tarifa cargada: el
          costo real es mayor.
        </p>
        <table class="su__table">
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              <th scope="col" class="su__num">Páginas</th>
              <th scope="col" class="su__num">Pedidos</th>
              <th scope="col" class="su__num">Tokens</th>
              <th scope="col" class="su__num">Costo</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in documents.per_model" :key="`${row.provider}-${row.model}`">
              <td>{{ row.provider }} · <code>{{ row.model }}</code></td>
              <td class="su__num">{{ formatTokens(row.pages) }}</td>
              <td class="su__num">{{ formatTokens(row.requests) }}</td>
              <td class="su__num">{{ formatTokens(row.input_tokens + row.output_tokens) }}</td>
              <td class="su__num su__num--strong">{{ formatCop(row.cost_usd, rate) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="su__ranking" aria-label="Consumo por proveedor">
        <h2 class="su__section-title">Chat por proveedor</h2>
        <ProviderBreakdown :rows="store.system.per_provider" :rate="rate" />
      </section>

      <section
        v-if="databaseRows.length > 0"
        class="su__ranking"
        aria-label="Consumo por cliente"
      >
        <h2 class="su__section-title">Por cliente (base consultada)</h2>
        <table class="su__table">
          <thead>
            <tr>
              <th scope="col">Base</th>
              <th scope="col" class="su__num">Respuestas</th>
              <th scope="col" class="su__num">Tokens</th>
              <th scope="col" class="su__num">Costo</th>
              <th scope="col" class="su__num">% del costo</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in databaseRows" :key="row.key">
              <td>{{ row.label }}</td>
              <td class="su__num">{{ formatTokens(row.responses) }}</td>
              <td class="su__num">{{ formatTokens(row.tokens) }}</td>
              <td class="su__num su__num--strong">{{ formatCop(row.costUsd, rate) }}</td>
              <td class="su__num">{{ row.share.toFixed(1) }}%</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section
        v-if="store.system.daily_by_provider.length > 0"
        class="su__ranking"
        aria-label="Consumo por día"
      >
        <h2 class="su__section-title">Por día</h2>
        <ProviderDailyChart :daily="store.system.daily_by_provider" :rate="rate" />
      </section>

      <section class="su__ranking" aria-label="Consumo por usuario">
        <h2 class="su__section-title">Por usuario</h2>
        <p v-if="store.system.per_user.length === 0" class="su__hint">
          Sin consumo en este período.
        </p>
        <table v-else class="su__table">
          <thead>
            <tr>
              <th scope="col">Usuario</th>
              <th scope="col" class="su__num">Tokens</th>
              <th scope="col" class="su__num">Respuestas</th>
              <th scope="col" class="su__num">Costo</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in store.system.per_user"
              :key="`${u.erp_database_id ?? 'legacy'}-${u.user_id ?? 'legacy'}`"
            >
              <td>{{ userLabel(u.user_id, u.erp_database_id) }}</td>
              <td class="su__num">{{ formatTokens(u.totals.total_tokens) }}</td>
              <td class="su__num">{{ formatTokens(u.totals.message_count) }}</td>
              <td class="su__num su__num--strong">{{ formatCop(u.totals.cost_usd, rate) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </section>
</template>

<style scoped>
.su__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.su__card {
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-xs);
}

.su__card--primary {
  background: var(--surface-elev);
  border-color: var(--border-strong, var(--border));
}

.su__card-label {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.su__card-value {
  margin: 0;
  font-family: var(--font-display, var(--font-sans));
  font-size: 26px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.su__card-foot {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.su__card-warning {
  margin: var(--space-2) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
  font-size: 12px;
  line-height: 1.4;
}

.su__ranking + .su__ranking {
  margin-top: var(--space-6);
}

.su__section-title {
  margin: 0 0 var(--space-3);
  font-size: 12px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.su__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.su__table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: var(--fw-medium);
  border-bottom: 1px solid var(--border);
}

.su__table td {
  padding: var(--space-3);
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.su__num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.su__num--strong {
  font-weight: var(--fw-semibold);
}

.su__hint {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--text-subtle);
}

.su__error {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}
</style>
