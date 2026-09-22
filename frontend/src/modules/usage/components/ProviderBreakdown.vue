<script setup lang="ts">
/**
 * Desglose de consumo por proveedor, expandible a modelo. Compartido entre
 * "Mi consumo" y el admin: mismos datos (`ProviderUsage[]`, siempre
 * agrupados por (proveedor, modelo)), la vista solo cambia el título.
 *
 * El origen del costo se marca por fila: Claude informa el costo real
 * (`total_cost_usd` del SDK), Gemini/OpenAI lo ESTIMAN con la tabla de
 * precios del admin — si no hay precio cargado, esas respuestas quedan
 * sin costo (`untariffed_count`) y hay que decirlo, no sumarlas como cero.
 */
import { computed, ref } from 'vue'
import ProviderIcon from '@/modules/admin/components/ProviderIcon.vue'
import type { ProviderUsage, UsageProviderKind } from '../types'
import { formatCop, formatTokens, formatUsd } from '../utils/format'
import { PROVIDER_LABELS, REPORTS_COST_BY_PROVIDER } from '../utils/providers'

const props = defineProps<{
  rows: ProviderUsage[]
  rate: number
}>()

interface ProviderGroup {
  provider: string
  kind: UsageProviderKind | null
  costUsd: number
  totalTokens: number
  messageCount: number
  untariffedCount: number
  models: { model: string; costUsd: number; totalTokens: number; messageCount: number }[]
}

const groups = computed<ProviderGroup[]>(() => {
  const byProvider = new Map<string, ProviderGroup>()
  for (const row of props.rows) {
    const key = row.provider ?? 'sin-proveedor'
    let group = byProvider.get(key)
    if (!group) {
      group = {
        provider: row.provider ?? 'Sin proveedor',
        kind: (row.provider?.toLowerCase() as UsageProviderKind) ?? null,
        costUsd: 0,
        totalTokens: 0,
        messageCount: 0,
        untariffedCount: 0,
        models: [],
      }
      byProvider.set(key, group)
    }
    group.costUsd += row.totals.cost_usd
    group.totalTokens += row.totals.total_tokens
    group.messageCount += row.totals.message_count
    group.untariffedCount += row.totals.untariffed_count
    group.models.push({
      model: row.model ?? 'Sin modelo',
      costUsd: row.totals.cost_usd,
      totalTokens: row.totals.total_tokens,
      messageCount: row.totals.message_count,
    })
  }
  for (const group of byProvider.values()) {
    group.models.sort((a, b) => b.costUsd - a.costUsd)
  }
  return [...byProvider.values()].sort((a, b) => b.costUsd - a.costUsd)
})

const grandTotalCostUsd = computed(() => groups.value.reduce((acc, g) => acc + g.costUsd, 0))

function sharePct(costUsd: number): number {
  if (grandTotalCostUsd.value <= 0) return 0
  return (costUsd / grandTotalCostUsd.value) * 100
}

function reportsCost(kind: UsageProviderKind | null): boolean {
  return kind !== null && REPORTS_COST_BY_PROVIDER[kind] === true
}

function providerLabel(group: ProviderGroup): string {
  return group.kind ? (PROVIDER_LABELS[group.kind] ?? group.provider) : group.provider
}

const expanded = ref<Set<string>>(new Set())

function toggle(provider: string): void {
  const next = new Set(expanded.value)
  if (next.has(provider)) next.delete(provider)
  else next.add(provider)
  expanded.value = next
}
</script>

<template>
  <div class="pb">
    <p v-if="groups.length === 0" class="pb__hint">Sin consumo en este período.</p>
    <ul v-else class="pb__list">
      <li v-for="group in groups" :key="group.provider" class="pb__group">
        <button
          type="button"
          class="pb__row"
          :aria-expanded="expanded.has(group.provider)"
          @click="toggle(group.provider)"
        >
          <span class="pb__chevron" :class="{ 'pb__chevron--open': expanded.has(group.provider) }">
            ›
          </span>
          <ProviderIcon v-if="group.kind" :kind="group.kind" :size="16" />
          <span class="pb__name">{{ providerLabel(group) }}</span>
          <span class="pb__bar-track">
            <span class="pb__bar" :style="{ width: `${sharePct(group.costUsd)}%` }" />
          </span>
          <span class="pb__tokens">{{ formatTokens(group.totalTokens) }} tok</span>
          <span class="pb__count">{{ formatTokens(group.messageCount) }} resp.</span>
          <span class="pb__cost">{{ formatCop(group.costUsd, rate) }}</span>
        </button>

        <p class="pb__origin">
          <span v-if="reportsCost(group.kind)">💲 El proveedor informa el costo real de cada respuesta.</span>
          <span v-else>Costo estimado con la tabla de precios cargada en Proveedores de IA.</span>
        </p>
        <p v-if="!reportsCost(group.kind) && group.untariffedCount > 0" class="pb__warning">
          {{ group.untariffedCount }}
          {{ group.untariffedCount === 1 ? 'respuesta' : 'respuestas' }} de
          {{ providerLabel(group) }} sin tarifa cargada — el costo real es mayor.
        </p>

        <ul v-if="expanded.has(group.provider)" class="pb__models">
          <li v-for="m in group.models" :key="m.model" class="pb__model-row">
            <code class="pb__model-name">{{ m.model }}</code>
            <span class="pb__tokens">{{ formatTokens(m.totalTokens) }} tok</span>
            <span class="pb__count">{{ formatTokens(m.messageCount) }} resp.</span>
            <span class="pb__cost">{{ formatUsd(m.costUsd) }}</span>
          </li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.pb__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.pb__row {
  display: grid;
  grid-template-columns: 14px auto 1fr minmax(90px, auto) minmax(90px, auto) minmax(90px, auto) minmax(96px, auto);
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-2) 0;
  background: transparent;
  border: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.pb__chevron {
  display: inline-block;
  color: var(--text-subtle);
  transition: transform var(--duration-fast) var(--ease-out);
}

.pb__chevron--open {
  transform: rotate(90deg);
}

.pb__name {
  font-weight: var(--fw-medium);
  color: var(--text);
}

.pb__bar-track {
  height: 6px;
  background: var(--surface-subtle);
  border-radius: 999px;
  overflow: hidden;
}

.pb__bar {
  display: block;
  height: 100%;
  background: var(--brand);
  border-radius: 999px;
}

.pb__tokens,
.pb__count {
  font-size: 12px;
  color: var(--text-muted);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.pb__cost {
  font-weight: var(--fw-semibold);
  color: var(--text);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.pb__origin {
  margin: 0 0 0 26px;
  font-size: 11px;
  color: var(--text-subtle);
}

.pb__warning {
  margin: var(--space-1) 0 0 26px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-warning, rgba(217, 119, 6, 0.1));
  color: var(--text-warning, #b45309);
  font-size: 12px;
  line-height: 1.4;
}

.pb__models {
  list-style: none;
  margin: var(--space-2) 0 0 26px;
  padding: var(--space-2) 0 0;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.pb__model-row {
  display: grid;
  grid-template-columns: 1fr minmax(90px, auto) minmax(90px, auto) minmax(96px, auto);
  align-items: center;
  gap: var(--space-3);
}

.pb__model-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.pb__hint {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--text-subtle);
}

@media (max-width: 620px) {
  .pb__row {
    grid-template-columns: 14px auto 1fr;
    row-gap: var(--space-2);
  }
  .pb__bar-track { display: none; }
  .pb__tokens, .pb__count, .pb__cost { grid-column: span 1; }
  .pb__model-row { grid-template-columns: 1fr; row-gap: 2px; }
}
</style>
