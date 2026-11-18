<script setup lang="ts">
import {
  Alert,
  Button,
  Card,
  PageHeader,
  Select,
  Skeleton,
  Switch,
  TextField,
  toast,
} from '@savi/ui'
import { ref } from 'vue'
import { consoleApi } from '@/lib/api'
import { SEVERITY } from '@/lib/format'
import type { AlertRule, Severity } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'

const { data, loading, error, reload } = useAsync(() => consoleApi.alertRules())

const SEVERITY_OPTIONS = (Object.keys(SEVERITY) as Severity[]).map((value) => ({
  value,
  label: SEVERITY[value].label,
}))

/** Umbral que se está editando por regla (antes de guardarlo). */
const drafts = ref<Record<string, number | null>>({})
const thresholdErrors = ref<Record<string, string | undefined>>({})
const busy = ref<string | null>(null)

async function save(
  rule: AlertRule,
  patch: { enabled?: boolean; threshold?: number; severity?: Severity },
  done: string,
): Promise<void> {
  busy.value = rule.code
  try {
    await consoleApi.updateRule(rule.code, patch)
    delete drafts.value[rule.code]
    toast.success(done)
    await reload()
  } catch (e) {
    toast.error('No se pudo guardar la regla', { description: errorMessage(e) })
  } finally {
    busy.value = null
  }
}

function draftOf(rule: AlertRule): number | null {
  return rule.code in drafts.value ? (drafts.value[rule.code] ?? null) : rule.threshold
}

function isDirty(rule: AlertRule): boolean {
  return rule.code in drafts.value && drafts.value[rule.code] !== rule.threshold
}

function saveThreshold(rule: AlertRule): void {
  const value = drafts.value[rule.code]
  if (value === null || value === undefined || Number.isNaN(value) || value <= 0) {
    thresholdErrors.value[rule.code] = 'El umbral tiene que ser un número mayor que cero.'
    return
  }
  thresholdErrors.value[rule.code] = undefined
  void save(rule, { threshold: value }, 'Umbral guardado')
}
</script>

<template>
  <div>
    <PageHeader
      title="Reglas de alerta"
      description="Cada cambio aplica desde la próxima evaluación (cada 5 minutos). Al apagar una regla se resuelven sus alertas abiertas."
    />

    <div class="stack">
      <Alert v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </Alert>

      <Card padding="none">
        <div v-if="loading && !data" class="loading">
          <Skeleton v-for="n in 4" :key="n" height="18px" />
        </div>

        <!-- Una fila por regla: lo que se cambia seguido (severidad, umbral, encendido)
             queda alineado en columnas; la explicación va debajo del nombre. -->
        <table v-else class="rules">
          <caption class="sr-only">Reglas de alerta</caption>
          <thead>
            <tr>
              <th scope="col">Regla</th>
              <th scope="col" class="col-severity">Severidad</th>
              <th scope="col" class="col-threshold">Umbral</th>
              <th scope="col" class="col-enabled">Activa</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in data ?? []" :key="rule.code" :class="{ 'rule--off': !rule.enabled }">
              <td class="rule">
                <strong>{{ rule.title }}</strong>
                <p>{{ rule.description }}</p>
                <small>{{ rule.auto_resolve ? 'Se resuelve sola' : 'Se resuelve a mano' }}</small>
              </td>
              <td class="col-severity" data-label="Severidad">
                <Select
                  class="compact"
                  :model-value="rule.severity"
                  :label="`Severidad de ${rule.title}`"
                  :options="SEVERITY_OPTIONS"
                  :disabled="busy === rule.code"
                  @update:model-value="(value) => value && save(rule, { severity: value }, 'Severidad guardada')"
                />
              </td>
              <td class="col-threshold" data-label="Umbral">
                <form
                  v-if="rule.default_threshold !== null"
                  class="threshold"
                  novalidate
                  @submit.prevent="saveThreshold(rule)"
                >
                  <TextField
                    class="compact"
                    :model-value="draftOf(rule)"
                    type="number"
                    :min="0"
                    step="any"
                    :label="`Umbral de ${rule.title}`"
                    :error="thresholdErrors[rule.code]"
                    :data-test="`rule-${rule.code}-threshold`"
                    @update:model-value="drafts[rule.code] = $event as number | null"
                  >
                    <template #suffix>{{ rule.threshold_unit }}</template>
                  </TextField>
                  <Button v-if="isDirty(rule)" type="submit" size="sm" :loading="busy === rule.code">
                    Guardar
                  </Button>
                  <small v-else class="muted">Por defecto: {{ rule.default_threshold }}</small>
                </form>
                <span v-else class="muted">—</span>
              </td>
              <td class="col-enabled" data-label="Activa">
                <Switch
                  class="compact"
                  :model-value="rule.enabled"
                  :label="rule.enabled ? 'Activa' : 'Apagada'"
                  :aria-label="`Regla ${rule.title}`"
                  :disabled="busy === rule.code"
                  :data-test="`rule-${rule.code}-enabled`"
                  @update:model-value="save(rule, { enabled: $event }, $event ? 'Regla activada' : 'Regla apagada')"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </Card>
    </div>
  </div>
</template>

<style scoped>
.loading {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-5);
}

.rules {
  width: 100%;
  border-collapse: collapse;
}

.rules th {
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--border);
  font-size: 11.5px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.04em;
  text-align: left;
  text-transform: uppercase;
  color: var(--text-muted);
}

.rules td {
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.rules tbody tr:last-child td {
  border-bottom: 0;
}

.rule strong {
  font-size: 14px;
}

.rule p {
  margin: 4px 0;
  max-width: 60ch;
  font-size: 12.5px;
  color: var(--text-muted);
}

.rule small {
  font-size: 12px;
  color: var(--text-subtle);
}

.col-severity {
  width: 170px;
}

.col-threshold {
  width: 260px;
}

.col-enabled {
  width: 130px;
}

/* En la tabla, la columna ya nombra cada campo: la etiqueta queda solo para lectores. */
.compact :deep(.ui-field__label),
.compact :deep(.ui-switch__label) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.threshold {
  display: grid;
  gap: var(--space-2);
  justify-items: start;
}

.threshold small {
  font-size: 12px;
}

.rule--off .rule,
.rule--off .col-severity,
.rule--off .col-threshold {
  opacity: 0.6;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 760px) {
  .rules thead {
    display: none;
  }

  .rules,
  .rules tbody,
  .rules tr,
  .rules td {
    display: block;
    width: auto;
  }

  .rules tr {
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border);
  }

  .rules td {
    padding: var(--space-2) var(--space-5);
    border: 0;
  }

  .rules td[data-label]::before {
    content: attr(data-label);
    display: block;
    margin-bottom: 4px;
    font-size: 11.5px;
    color: var(--text-muted);
  }
}
</style>
