<script setup lang="ts">
import { Badge, Card } from '@savi/ui'
import { Check, CircleCheck } from 'lucide-vue-next'
import { computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { consoleApi } from '@/lib/api'
import { buildOnboardingSteps } from '@/lib/onboarding'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

/**
 * "Puesta en marcha" de un cliente nuevo: cada paso se marca solo con lo que Cloud ya sabe.
 * Al completarse queda una línea; si no carga, no estorba: los KPIs de abajo no dependen de esto.
 */
const props = defineProps<{ clientId: string }>()

const auth = useAuthStore()
const onboarding = useAsync(() => consoleApi.clientOnboarding(props.clientId))
watch(
  () => props.clientId,
  () => onboarding.reload(),
)

const steps = computed(() =>
  onboarding.data.value ? buildOnboardingSteps(onboarding.data.value, auth.can) : [],
)
const doneCount = computed(() => steps.value.filter((s) => s.done).length)
const complete = computed(() => steps.value.length > 0 && doneCount.value === steps.value.length)
/** El primer paso pendiente que esta persona puede hacer: lo que sigue. */
const nextKey = computed(() => steps.value.find((s) => !s.done && !s.pendingRole)?.key ?? null)
</script>

<template>
  <p v-if="complete" class="onboarding-done" data-test="onboarding-complete">
    <CircleCheck :size="15" aria-hidden="true" /> Puesta en marcha completa
  </p>

  <Card
    v-else-if="steps.length"
    title="Puesta en marcha"
    :description="`${doneCount} de ${steps.length} pasos completos. Se marcan solos a medida que avanza la instalación.`"
    data-test="onboarding"
  >
    <ol class="onboarding">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="onboarding__step"
        :class="{ 'onboarding__step--done': step.done }"
        :data-test="`onboarding-${step.key}`"
        :data-state="step.done ? 'done' : 'pending'"
      >
        <span class="onboarding__marker" aria-hidden="true">
          <Check v-if="step.done" :size="12" :stroke-width="3" />
          <template v-else>{{ index + 1 }}</template>
        </span>
        <div class="onboarding__body">
          <p class="onboarding__label">
            <span v-if="step.done">{{ step.label }}</span>
            <span v-else-if="step.pendingRole">{{ step.label }}</span>
            <RouterLink v-else :to="`/clientes/${clientId}/${step.tab}`">{{ step.label }}</RouterLink>
            <span v-if="step.done" class="sr-only"> (listo)</span>
            <Badge v-if="step.key === nextKey" tone="brand">Siguiente</Badge>
            <Badge v-else-if="step.pendingRole" tone="neutral" data-test="onboarding-role">
              Pendiente de {{ step.pendingRole }}
            </Badge>
          </p>
          <p v-if="!step.done" class="onboarding__hint">{{ step.hint }}</p>
        </div>
      </li>
    </ol>
  </Card>
</template>

<style scoped>
.onboarding-done {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  color: var(--success);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}

.onboarding {
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.onboarding__step {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.onboarding__marker {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: 1.5px solid var(--border-strong);
  border-radius: 50%;
  color: var(--text-muted);
  font-size: 11px;
}

.onboarding__step--done .onboarding__marker {
  border-color: var(--success);
  background: var(--success);
  color: var(--surface-elev);
}

.onboarding__step--done .onboarding__label {
  color: var(--text-muted);
}

.onboarding__body {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.onboarding__label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
}

.onboarding__hint {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
