<script setup lang="ts">
import { Button, Card, Skeleton, Alert as UiAlert } from '@savi/ui'
import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { alertDetail } from '@/lib/alertDetails'
import { consoleApi } from '@/lib/api'
import { clientPath } from '@/lib/clientRoutes'
import { relativeTime, SEVERITY } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'
import type { Alert, Severity } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'

/**
 * "¿Qué tengo que atender hoy?": las alertas abiertas más urgentes, cada una con su
 * cliente y el enlace para resolverla. Las reconocidas ya tienen a alguien encima.
 */
const SHOWN = 5
const RANK: Record<Severity, number> = { critical: 0, warning: 1, info: 2 }
const ICON = { critical: CircleAlert, warning: TriangleAlert, info: Info } as const

const ruleTitle = useRuleTitles()
const { data, loading, error, reload } = useAsync(() => consoleApi.alerts({ status: 'open' }))

const sorted = computed<Alert[]>(() =>
  [...(data.value ?? [])].sort(
    (a, b) => RANK[a.severity] - RANK[b.severity] || b.opened_at.localeCompare(a.opened_at),
  ),
)
const shown = computed(() => sorted.value.slice(0, SHOWN))
const rest = computed(() => Math.max(0, sorted.value.length - SHOWN))
</script>

<template>
  <Card title="Requiere atención" padding="none" data-test="attention">
    <template #actions>
      <RouterLink v-if="sorted.length" to="/alertas" class="more">Ver todas las alertas</RouterLink>
    </template>

    <div v-if="loading && !data" class="pad">
      <Skeleton height="14px" width="70%" />
      <Skeleton height="14px" width="55%" style="margin-top: 10px" />
    </div>

    <div v-else-if="error" class="pad">
      <UiAlert tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </UiAlert>
    </div>

    <p v-else-if="!sorted.length" class="calm" data-test="attention-empty">
      <CircleCheck :size="16" aria-hidden="true" />
      Nada pendiente: no hay alertas abiertas.
    </p>

    <ul v-else class="items">
      <li v-for="alert in shown" :key="alert.id" class="item" :class="`item--${alert.severity}`">
        <component :is="ICON[alert.severity]" :size="16" class="icon" :aria-label="SEVERITY[alert.severity].label" />
        <div class="body">
          <strong>{{ ruleTitle(alert.rule_code) }}</strong>
          <span v-if="Object.keys(alert.details).length" class="detail">{{ alertDetail(alert) }}</span>
        </div>
        <RouterLink :to="clientPath(alert.client_id, 'alertas')" class="client">
          {{ alert.client_name ?? 'Ver cliente' }}
        </RouterLink>
        <span class="when">{{ relativeTime(alert.opened_at) }}</span>
      </li>
      <li v-if="rest" class="item item--rest">
        <RouterLink to="/alertas">Y {{ rest }} {{ rest === 1 ? 'alerta más' : 'alertas más' }}</RouterLink>
      </li>
    </ul>
  </Card>
</template>

<style scoped>
.pad {
  padding: var(--space-5);
}

.more {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}

.calm {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-5);
  color: var(--text-muted);
}

.calm svg {
  color: var(--text-success);
}

.items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  border-top: 1px solid var(--border);
  font-size: 13.5px;
}

.item:first-child {
  border-top: 0;
}

.icon {
  color: var(--text-muted);
}

.item--critical .icon {
  color: var(--text-danger);
}

.item--warning .icon {
  color: var(--text-warning);
}

.body {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: var(--text-muted);
}

.client {
  text-decoration: underline;
  text-decoration-color: var(--border-strong);
  text-underline-offset: 3px;
}

.when {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.item--rest {
  display: block;
  font-size: 12.5px;
}

@media (max-width: 640px) {
  .item {
    grid-template-columns: 20px minmax(0, 1fr);
  }

  .client,
  .when {
    grid-column: 2;
  }
}
</style>
