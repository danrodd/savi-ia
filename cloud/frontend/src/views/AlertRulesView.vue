<script setup lang="ts">
import { ref } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import type { AlertRule, Severity } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'

const { data, error, reload } = useAsync(() => consoleApi.alertRules())
const actionError = ref<string | null>(null)
const drafts = ref<Record<string, string>>({})

async function save(
  rule: AlertRule,
  patch: { enabled?: boolean; threshold?: number; severity?: Severity },
): Promise<void> {
  actionError.value = null
  try {
    await consoleApi.updateRule(rule.code, patch)
    delete drafts.value[rule.code]
    await reload()
  } catch (e) {
    actionError.value = errorMessage(e)
  }
}

function saveThreshold(rule: AlertRule): void {
  const raw = drafts.value[rule.code]
  const value = Number(raw)
  if (raw === undefined || Number.isNaN(value)) return
  void save(rule, { threshold: value })
}
</script>

<template>
  <div class="stack">
    <h1>Reglas de alerta</h1>
    <p class="muted">
      Cambiar un umbral o desactivar una regla aplica desde la próxima evaluación (cada 5
      minutos). Al desactivar una regla se resuelven sus alertas abiertas.
    </p>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="actionError" class="error-text" role="alert">{{ actionError }}</p>

    <div class="stack">
      <section v-for="rule in data ?? []" :key="rule.code" class="card rule">
        <div class="spread">
          <div>
            <h2>{{ rule.title }}</h2>
            <p class="muted">{{ rule.description }}</p>
          </div>
          <label class="switch">
            <input
              type="checkbox"
              :checked="rule.enabled"
              @change="save(rule, { enabled: ($event.target as HTMLInputElement).checked })"
            />
            {{ rule.enabled ? 'Activa' : 'Apagada' }}
          </label>
        </div>
        <div class="row">
          <label v-if="rule.default_threshold !== null" class="threshold">
            Umbral ({{ rule.threshold_unit }})
            <span class="row">
              <input
                type="number"
                step="any"
                min="0"
                :value="drafts[rule.code] ?? rule.threshold ?? ''"
                @input="drafts[rule.code] = ($event.target as HTMLInputElement).value"
              />
              <button class="btn btn-small" type="button" @click="saveThreshold(rule)">
                Guardar
              </button>
            </span>
          </label>
          <label class="severity">
            Severidad
            <select
              :value="rule.severity"
              @change="save(rule, { severity: ($event.target as HTMLSelectElement).value as Severity })"
            >
              <option value="info">Info</option>
              <option value="warning">Aviso</option>
              <option value="critical">Crítica</option>
            </select>
          </label>
          <StatusBadge
            :tone="rule.auto_resolve ? 'ok' : 'muted'"
            :label="rule.auto_resolve ? 'Se resuelve sola' : 'Se resuelve a mano'"
          />
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.rule {
  display: grid;
  gap: 0.8rem;
}
.rule p {
  margin: 0.2rem 0 0;
}
.switch {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--text);
}
.switch input {
  width: auto;
}
.threshold {
  max-width: 280px;
}
.severity {
  max-width: 180px;
}
</style>
