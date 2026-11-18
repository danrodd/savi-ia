<script setup lang="ts">
import { Badge } from '@savi/ui'
import { Check, ChevronDown } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { consoleApi } from '@/lib/api'
import { clientPath } from '@/lib/clientRoutes'
import { buildOnboardingSteps } from '@/lib/onboarding'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

/**
 * "Puesta en marcha" de un cliente nuevo: cada paso se marca solo con lo que Cloud ya sabe.
 * Es una barra compacta ("3 de 6 · Siguiente: …") que se despliega al hacer clic, y desaparece
 * al completarse. Si no carga, no estorba: los KPIs de abajo no dependen de esto.
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
const nextLabel = computed(() => steps.value.find((s) => s.key === nextKey.value)?.label ?? null)
const progress = computed(() =>
  steps.value.length ? Math.round((doneCount.value / steps.value.length) * 100) : 0,
)
const expanded = ref(false)
</script>

<template>
  <section v-if="steps.length && !complete" class="onboarding-bar" data-test="onboarding">
    <button
      type="button"
      class="onboarding-bar__head"
      :aria-expanded="expanded"
      aria-controls="onboarding-steps"
      data-test="onboarding-toggle"
      @click="expanded = !expanded"
    >
      <span class="onboarding-bar__title">Puesta en marcha</span>
      <span class="onboarding-bar__count">{{ doneCount }} de {{ steps.length }}</span>
      <span class="onboarding-bar__track" aria-hidden="true">
        <span class="onboarding-bar__fill" :style="{ width: `${progress}%` }" />
      </span>
      <span v-if="nextLabel" class="onboarding-bar__next">Siguiente: {{ nextLabel }}</span>
      <ChevronDown :size="16" class="onboarding-bar__chevron" :class="{ open: expanded }" aria-hidden="true" />
    </button>

    <ol v-show="expanded" id="onboarding-steps" class="onboarding">
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
            <RouterLink v-else :to="clientPath(clientId, step.tab)">{{ step.label }}</RouterLink>
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
  </section>
</template>

<style scoped>
.onboarding-bar {
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface-elev);
}

.onboarding-bar__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-4);
  width: 100%;
  padding: var(--space-3) var(--space-5);
  border: 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.onboarding-bar__head:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: -2px;
  border-radius: var(--r-lg);
}

.onboarding-bar__title {
  font-weight: var(--fw-semibold, 600);
}

.onboarding-bar__count {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.onboarding-bar__track {
  flex: 1 1 120px;
  max-width: 240px;
  height: 6px;
  border-radius: 999px;
  background: var(--border);
  overflow: hidden;
}

.onboarding-bar__fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--success);
}

.onboarding-bar__next {
  color: var(--text-muted);
}

.onboarding-bar__chevron {
  margin-left: auto;
  color: var(--text-muted);
  transition: transform 150ms ease;
}

.onboarding-bar__chevron.open {
  transform: rotate(180deg);
}

.onboarding {
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: var(--space-2) var(--space-5) var(--space-5);
  border-top: 1px solid var(--border);
  padding-top: var(--space-4);
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
