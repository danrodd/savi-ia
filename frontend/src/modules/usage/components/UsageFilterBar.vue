<script setup lang="ts">
/**
 * Filtro compartido de las vistas de consumo: rango de fechas (con los
 * presets Hoy/Ayer, pensados para cuadrar contra el crédito cargado en un
 * proveedor) + selección múltiple de proveedor. Todo lo que consuma esto
 * responde al mismo filtro: costo total, tokens, serie diaria y desglose.
 *
 * Los administradores además filtran por cliente (base consultada): soporte
 * atiende a varios desde una sola sesión.
 */

import { computed, onMounted, ref } from 'vue'
import ProviderIcon from '@/modules/admin/components/ProviderIcon.vue'
import { useErpDatabaseStore } from '@/modules/admin/stores/erpDatabaseStore'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import { type RangePreset, useUsageStore } from '../stores/usageStore'
import type { UsageProviderKind } from '../types'
import { PROVIDER_LABELS, USAGE_PROVIDERS } from '../utils/providers'

const store = useUsageStore()
const authStore = useAuthStore()
const databaseStore = useErpDatabaseStore()

// Solo tiene sentido con más de un cliente, y el listado de bases es de
// administración: un usuario común no lo puede pedir.
const showDatabases = computed(
  () => !!authStore.user?.is_admin && databaseStore.databases.length > 1,
)
const databaseOptions = computed(() =>
  [...databaseStore.databases].sort((a, b) => a.code.localeCompare(b.code)),
)

onMounted(() => {
  if (authStore.user?.is_admin && databaseStore.databases.length === 0 && !databaseStore.loading) {
    void databaseStore.load()
  }
})

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: 'today', label: 'Hoy' },
  { value: 'yesterday', label: 'Ayer' },
  { value: 7, label: '7 días' },
  { value: 30, label: '30 días' },
  { value: 90, label: '90 días' },
  { value: 'custom', label: 'Personalizado' },
]

const draftFrom = ref(store.customFrom)
const draftTo = ref(store.customTo)
const isCustom = computed(() => store.preset === 'custom')

function selectPreset(preset: RangePreset): void {
  if (preset === 'custom') {
    draftFrom.value = store.customFrom
    draftTo.value = store.customTo
  }
  void store.setPreset(preset)
}

function applyCustomRange(): void {
  if (!draftFrom.value || !draftTo.value) return
  void store.setCustomRange(draftFrom.value, draftTo.value)
}

function toggleProvider(provider: UsageProviderKind): void {
  const current = store.providers
  const next = current.includes(provider)
    ? current.filter((p) => p !== provider)
    : [...current, provider]
  void store.setProviders(next)
}

function toggleDatabase(id: string): void {
  const current = store.databases
  const next = current.includes(id) ? current.filter((d) => d !== id) : [...current, id]
  void store.setDatabases(next)
}
</script>

<template>
  <div class="ufb">
    <div class="ufb__presets" role="tablist" aria-label="Rango de tiempo">
      <button
        v-for="p in PRESETS"
        :key="String(p.value)"
        type="button"
        role="tab"
        class="ufb__preset"
        :class="{ 'ufb__preset--active': store.preset === p.value }"
        :aria-selected="store.preset === p.value"
        @click="selectPreset(p.value)"
      >
        {{ p.label }}
      </button>
    </div>

    <div v-if="isCustom" class="ufb__custom">
      <label class="ufb__date-field">
        Desde
        <input v-model="draftFrom" type="date" :max="draftTo || undefined" @change="applyCustomRange" />
      </label>
      <label class="ufb__date-field">
        Hasta
        <input v-model="draftTo" type="date" :min="draftFrom || undefined" @change="applyCustomRange" />
      </label>
    </div>

    <div class="ufb__providers" role="group" aria-label="Filtrar por proveedor">
      <button
        v-for="provider in USAGE_PROVIDERS"
        :key="provider"
        type="button"
        class="ufb__provider-chip"
        :class="{ 'ufb__provider-chip--active': store.providers.includes(provider) }"
        :aria-pressed="store.providers.includes(provider)"
        @click="toggleProvider(provider)"
      >
        <ProviderIcon :kind="provider" :size="14" />
        {{ PROVIDER_LABELS[provider] }}
      </button>
    </div>

    <div v-if="showDatabases" class="ufb__providers" role="group" aria-label="Filtrar por cliente">
      <button
        v-for="db in databaseOptions"
        :key="db.id"
        type="button"
        class="ufb__provider-chip"
        :class="{ 'ufb__provider-chip--active': store.databases.includes(db.id) }"
        :aria-pressed="store.databases.includes(db.id)"
        :title="db.name"
        @click="toggleDatabase(db.id)"
      >
        {{ db.code }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.ufb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ufb__presets {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 3px;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.ufb__preset {
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
  white-space: nowrap;
}

.ufb__preset:hover {
  color: var(--text);
}

.ufb__preset--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.ufb__custom {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.ufb__date-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.ufb__date-field input {
  min-height: 32px;
  padding: 0 var(--space-2);
  color: var(--text);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font: inherit;
  text-transform: none;
  letter-spacing: normal;
}

.ufb__providers {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ufb__provider-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  color: var(--text-muted);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.ufb__provider-chip:hover {
  color: var(--text);
  border-color: var(--border-strong, var(--border));
}

.ufb__provider-chip--active {
  color: var(--text);
  background: var(--brand-soft);
  border-color: var(--brand);
}

@media (max-width: 620px) {
  .ufb { flex-direction: column; align-items: stretch; }
  .ufb__presets, .ufb__providers { width: 100%; }
}
</style>
