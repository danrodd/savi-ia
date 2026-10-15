<script setup lang="ts">
import {
  Alert,
  Badge,
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

      <template v-if="loading && !data">
        <Card v-for="n in 3" :key="n">
          <Skeleton height="18px" width="35%" />
          <Skeleton height="14px" width="70%" style="margin-top: 10px" />
        </Card>
      </template>

      <Card v-for="rule in data ?? []" :key="rule.code" :class="{ 'rule--off': !rule.enabled }">
        <div class="rule">
          <div class="rule__head">
            <div class="rule__title">
              <h2>{{ rule.title }}</h2>
              <Badge :tone="rule.auto_resolve ? 'success' : 'neutral'">
                {{ rule.auto_resolve ? 'Se resuelve sola' : 'Se resuelve a mano' }}
              </Badge>
            </div>
            <p>{{ rule.description }}</p>
          </div>
          <Switch
            :model-value="rule.enabled"
            :label="rule.enabled ? 'Activa' : 'Apagada'"
            :aria-label="`Regla ${rule.title}`"
            :disabled="busy === rule.code"
            :data-test="`rule-${rule.code}-enabled`"
            @update:model-value="save(rule, { enabled: $event }, $event ? 'Regla activada' : 'Regla apagada')"
          />
        </div>

        <div class="rule__settings">
          <Select
            :model-value="rule.severity"
            label="Severidad"
            :options="SEVERITY_OPTIONS"
            :disabled="busy === rule.code"
            @update:model-value="(value) => value && save(rule, { severity: value }, 'Severidad guardada')"
          />
          <form
            v-if="rule.default_threshold !== null"
            class="rule__threshold"
            novalidate
            @submit.prevent="saveThreshold(rule)"
          >
            <TextField
              :model-value="draftOf(rule)"
              type="number"
              :min="0"
              step="any"
              :label="`Umbral (${rule.threshold_unit})`"
              :hint="`Por defecto: ${rule.default_threshold}`"
              :error="thresholdErrors[rule.code]"
              :data-test="`rule-${rule.code}-threshold`"
              @update:model-value="drafts[rule.code] = $event as number | null"
            />
            <Button
              v-if="isDirty(rule)"
              type="submit"
              class="rule__save"
              :loading="busy === rule.code"
            >
              Guardar umbral
            </Button>
          </form>
        </div>
      </Card>
    </div>
  </div>
</template>

<style scoped>
.rule {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-6);
}

.rule__head {
  min-width: 0;
}

.rule__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.rule__title h2 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: var(--fw-semibold);
}

.rule__head p {
  margin: var(--space-2) 0 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 70ch;
}

.rule__settings {
  display: grid;
  grid-template-columns: minmax(0, 200px) minmax(0, 1fr);
  align-items: start;
  gap: var(--space-5);
  margin-top: var(--space-5);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
}

.rule__threshold {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  max-width: 420px;
}

.rule__threshold > :first-child {
  flex: 1;
}

.rule__save {
  margin-top: 21px;
}

.rule--off {
  opacity: 0.75;
}

@media (max-width: 640px) {
  .rule {
    flex-direction: column;
  }

  .rule__settings {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
