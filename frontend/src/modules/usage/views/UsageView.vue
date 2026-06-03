<script setup lang="ts">
/**
 * UsageView — consumo del usuario y, para admins, del sistema.
 *
 * El backend reporta costo en USD + la tasa `usd_to_cop_rate`. Acá se
 * muestra el equivalente en COP como cifra principal (es lo que el
 * usuario final entiende), con el USD como referencia secundaria.
 */
import { computed, onMounted, ref } from 'vue'

import { useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import { type RangeDays, useUsageStore } from '@/modules/usage'
import type { DailyUsage } from '../types'
import { formatCop, formatDay, formatTokens, formatUsd } from '../utils/format'

type Tab = 'mine' | 'system'

const router = useRouter()
const authStore = useAuthStore()
const usageStore = useUsageStore()

const tab = ref<Tab>('mine')
const isAdmin = computed(() => authStore.user?.is_admin ?? false)

const RANGES: { value: RangeDays; label: string }[] = [
  { value: 7, label: '7 días' },
  { value: 30, label: '30 días' },
  { value: 90, label: '90 días' },
]

const rate = computed(() => usageStore.usdToCopRate)

const dailyMax = computed(() => {
  const source: DailyUsage[] =
    tab.value === 'system' ? (usageStore.system?.daily ?? []) : (usageStore.mine?.daily ?? [])
  return source.reduce((max, d) => Math.max(max, d.totals.cost_usd), 0)
})

function barWidth(costUsd: number): string {
  if (dailyMax.value <= 0) return '0%'
  return `${Math.max(2, (costUsd / dailyMax.value) * 100)}%`
}

async function selectTab(next: Tab): Promise<void> {
  tab.value = next
  if (next === 'system' && !usageStore.system && !usageStore.loadingSystem) {
    await usageStore.loadSystem()
  }
}

async function onRange(days: RangeDays): Promise<void> {
  await usageStore.setRange(days)
}

function goBack(): void {
  if (window.history.length > 1) router.back()
  else void router.push({ name: 'home' })
}

function userLabel(userId: number | null): string {
  if (userId === null) return 'Sin usuario (legado)'
  if (userId === authStore.user?.id) return `#${userId} · vos`
  return `#${userId}`
}

onMounted(() => {
  void usageStore.loadMine()
})
</script>

<template>
  <div class="usage">
    <div class="usage__container">
      <button type="button" class="usage__back" aria-label="Volver" @click="goBack">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Volver
      </button>

      <header class="usage__header">
        <h1 class="usage__title">Consumo</h1>
        <p class="usage__subtitle">
          Tokens y costo de tus interacciones con SAVI. El costo se calcula
          en dólares y se muestra convertido a pesos.
        </p>
      </header>

      <div class="usage__controls">
        <div v-if="isAdmin" class="usage__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            class="usage__tab"
            :class="{ 'usage__tab--active': tab === 'mine' }"
            :aria-selected="tab === 'mine'"
            @click="selectTab('mine')"
          >
            Mi consumo
          </button>
          <button
            type="button"
            role="tab"
            class="usage__tab"
            :class="{ 'usage__tab--active': tab === 'system' }"
            :aria-selected="tab === 'system'"
            @click="selectTab('system')"
          >
            Global
          </button>
        </div>

        <div class="usage__ranges" aria-label="Rango de tiempo">
          <button
            v-for="r in RANGES"
            :key="r.value"
            type="button"
            class="usage__range"
            :class="{ 'usage__range--active': usageStore.rangeDays === r.value }"
            @click="onRange(r.value)"
          >
            {{ r.label }}
          </button>
        </div>
      </div>

      <!-- ── Mi consumo ─────────────────────────────────────────────── -->
      <section v-if="tab === 'mine'" class="usage__panel" aria-label="Mi consumo">
        <p v-if="usageStore.loadingMine" class="usage__hint">Cargando…</p>
        <p v-else-if="usageStore.errorMine" class="usage__error" role="alert">
          {{ usageStore.errorMine }}
        </p>
        <template v-else-if="usageStore.mine">
          <div class="usage__cards">
            <article class="usage__card usage__card--primary">
              <p class="usage__card-label">Costo total</p>
              <p class="usage__card-value">
                {{ formatCop(usageStore.mine.totals.cost_usd, rate) }}
              </p>
              <p class="usage__card-foot">
                {{ formatUsd(usageStore.mine.totals.cost_usd) }} USD
              </p>
            </article>
            <article class="usage__card">
              <p class="usage__card-label">Tokens totales</p>
              <p class="usage__card-value">
                {{ formatTokens(usageStore.mine.totals.total_tokens) }}
              </p>
              <p class="usage__card-foot">
                {{ formatTokens(usageStore.mine.totals.message_count) }} respuestas
              </p>
            </article>
          </div>

          <div class="usage__tokens">
            <div class="usage__token">
              <span class="usage__token-label">Entrada</span>
              <span class="usage__token-value">
                {{ formatTokens(usageStore.mine.totals.input_tokens) }}
              </span>
            </div>
            <div class="usage__token">
              <span class="usage__token-label">Salida</span>
              <span class="usage__token-value">
                {{ formatTokens(usageStore.mine.totals.output_tokens) }}
              </span>
            </div>
            <div class="usage__token">
              <span class="usage__token-label">Caché (lectura)</span>
              <span class="usage__token-value">
                {{ formatTokens(usageStore.mine.totals.cache_read_input_tokens) }}
              </span>
            </div>
            <div class="usage__token">
              <span class="usage__token-label">Caché (escritura)</span>
              <span class="usage__token-value">
                {{ formatTokens(usageStore.mine.totals.cache_creation_input_tokens) }}
              </span>
            </div>
          </div>

          <section class="usage__daily" aria-label="Consumo por día">
            <h2 class="usage__section-title">Por día</h2>
            <p v-if="usageStore.mine.daily.length === 0" class="usage__hint">
              Sin consumo en este período.
            </p>
            <ul v-else class="usage__day-list">
              <li v-for="d in usageStore.mine.daily" :key="d.day" class="usage__day">
                <span class="usage__day-date">{{ formatDay(d.day) }}</span>
                <span class="usage__day-bar-track">
                  <span class="usage__day-bar" :style="{ width: barWidth(d.totals.cost_usd) }" />
                </span>
                <span class="usage__day-cost">
                  {{ formatCop(d.totals.cost_usd, rate) }}
                </span>
              </li>
            </ul>
          </section>
        </template>
      </section>

      <!-- ── Global (admin) ─────────────────────────────────────────── -->
      <section v-else class="usage__panel" aria-label="Consumo global">
        <p v-if="usageStore.loadingSystem" class="usage__hint">Cargando…</p>
        <p v-else-if="usageStore.errorSystem" class="usage__error" role="alert">
          {{ usageStore.errorSystem }}
        </p>
        <template v-else-if="usageStore.system">
          <div class="usage__cards">
            <article class="usage__card usage__card--primary">
              <p class="usage__card-label">Costo total del sistema</p>
              <p class="usage__card-value">
                {{ formatCop(usageStore.system.totals.cost_usd, rate) }}
              </p>
              <p class="usage__card-foot">
                {{ formatUsd(usageStore.system.totals.cost_usd) }} USD
              </p>
            </article>
            <article class="usage__card">
              <p class="usage__card-label">Tokens totales</p>
              <p class="usage__card-value">
                {{ formatTokens(usageStore.system.totals.total_tokens) }}
              </p>
              <p class="usage__card-foot">
                {{ formatTokens(usageStore.system.totals.message_count) }} respuestas
              </p>
            </article>
          </div>

          <section class="usage__ranking" aria-label="Consumo por usuario">
            <h2 class="usage__section-title">Por usuario</h2>
            <p v-if="usageStore.system.per_user.length === 0" class="usage__hint">
              Sin consumo en este período.
            </p>
            <table v-else class="usage__table">
              <thead>
                <tr>
                  <th scope="col">Usuario</th>
                  <th scope="col" class="usage__num">Tokens</th>
                  <th scope="col" class="usage__num">Respuestas</th>
                  <th scope="col" class="usage__num">Costo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in usageStore.system.per_user" :key="u.user_id ?? 'legacy'">
                  <td>{{ userLabel(u.user_id) }}</td>
                  <td class="usage__num">{{ formatTokens(u.totals.total_tokens) }}</td>
                  <td class="usage__num">{{ formatTokens(u.totals.message_count) }}</td>
                  <td class="usage__num usage__num--strong">
                    {{ formatCop(u.totals.cost_usd, rate) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
        </template>
      </section>

      <p class="usage__rate-note">
        Conversión a la tasa de {{ formatCop(1, rate) }} por USD (configurable
        por el administrador). El dato fuente del costo es siempre en dólares.
      </p>

      <div v-if="!authStore.user" class="usage__empty">
        <p>No hay sesión activa.</p>
        <Button @click="() => router.push({ name: 'login' })">Ir al login</Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.usage {
  min-height: 100vh;
  background: var(--bg);
  padding: var(--space-6);
  display: flex;
  justify-content: center;
}

.usage__container {
  width: min(820px, 100%);
}

.usage__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  margin-bottom: var(--space-5);
}

.usage__back:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.usage__header {
  margin-bottom: var(--space-6);
}

.usage__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.usage__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 56ch;
  line-height: 1.5;
}

.usage__controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}

.usage__tabs,
.usage__ranges {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.usage__tab,
.usage__range {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.usage__tab:hover,
.usage__range:hover {
  color: var(--text);
}

.usage__tab--active,
.usage__range--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.usage__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.usage__card {
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-xs);
}

.usage__card--primary {
  background: var(--surface-elev);
  border-color: var(--border-strong, var(--border));
}

.usage__card-label {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.usage__card-value {
  margin: 0;
  font-family: var(--font-display, var(--font-sans));
  font-size: 26px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.usage__card-foot {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.usage__tokens {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow: hidden;
  margin-bottom: var(--space-6);
}

.usage__token {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-elev);
}

.usage__token-label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.usage__token-value {
  font-size: 15px;
  font-weight: var(--fw-medium);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.usage__section-title {
  margin: 0 0 var(--space-3);
  font-size: 12px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.usage__day-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.usage__day {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  align-items: center;
  gap: var(--space-3);
}

.usage__day-date {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.usage__day-bar-track {
  height: 8px;
  background: var(--surface-subtle);
  border-radius: 999px;
  overflow: hidden;
}

.usage__day-bar {
  display: block;
  height: 100%;
  background: var(--brand);
  border-radius: 999px;
  transition: width var(--duration-slow) var(--ease-out);
}

.usage__day-cost {
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.usage__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.usage__table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: var(--fw-medium);
  border-bottom: 1px solid var(--border);
}

.usage__table td {
  padding: var(--space-3);
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.usage__num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.usage__num--strong {
  font-weight: var(--fw-semibold);
}

.usage__hint {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--text-subtle);
}

.usage__error {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.usage__rate-note {
  margin: var(--space-6) 0 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.5;
}

.usage__empty {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-6) 0;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
