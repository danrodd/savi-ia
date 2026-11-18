<script setup lang="ts">
import { Popover } from '@savi/ui'
import { Bell, CircleAlert, Info, TriangleAlert } from 'lucide-vue-next'
import { computed, ref, useTemplateRef } from 'vue'
import { RouterLink } from 'vue-router'
import { openAlertList, openAlerts } from '@/composables/useOpenAlerts'
import { clientPath } from '@/lib/clientRoutes'
import { relativeTime, SEVERITY } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'

/**
 * Campana de avisos: las alertas abiertas más recientes, a un clic desde cualquier pantalla.
 * Los datos los mantiene `useOpenAlerts` (la consola los relee cada 30 s).
 */
const SHOWN = 6
const ICON = { critical: CircleAlert, warning: TriangleAlert, info: Info } as const

const ruleTitle = useRuleTitles()
const open = ref(false)
const trigger = useTemplateRef<HTMLButtonElement>('trigger')

const count = computed(() => openAlerts.value ?? 0)
const latest = computed(() => openAlertList.value.slice(0, SHOWN))
const label = computed(() =>
  count.value === 0
    ? 'Avisos: no hay alertas abiertas'
    : `Avisos: ${count.value} ${count.value === 1 ? 'alerta abierta' : 'alertas abiertas'}`,
)
</script>

<template>
  <button
    ref="trigger"
    type="button"
    class="bell"
    :aria-label="label"
    :title="label"
    aria-haspopup="dialog"
    :aria-expanded="open"
    data-test="alert-bell"
    @click="open = !open"
  >
    <Bell :size="17" aria-hidden="true" />
    <span v-if="count" class="bell__count" aria-hidden="true">{{ count > 99 ? '99+' : count }}</span>
  </button>
  <Popover v-model:open="open" :anchor="trigger" align="start" side="bottom" :min-width="320">
    <div class="feed" role="dialog" aria-label="Avisos" data-test="alert-feed">
      <p class="feed__title">Avisos</p>
      <p v-if="!latest.length" class="feed__empty">No hay alertas abiertas.</p>
      <ul v-else class="feed__list">
        <li v-for="alert in latest" :key="alert.id">
          <RouterLink :to="clientPath(alert.client_id, 'alertas')" class="feed__item" @click="open = false">
            <component
              :is="ICON[alert.severity]"
              :size="15"
              class="feed__icon"
              :class="`feed__icon--${alert.severity}`"
              :aria-label="SEVERITY[alert.severity].label"
            />
            <span class="feed__body">
              <strong>{{ ruleTitle(alert.rule_code) }}</strong>
              <small>{{ alert.client_name ?? 'Cliente' }} · {{ relativeTime(alert.opened_at) }}</small>
            </span>
          </RouterLink>
        </li>
      </ul>
      <RouterLink to="/alertas" class="feed__all" @click="open = false">Ver todas las alertas</RouterLink>
    </div>
  </Popover>
</template>

<style scoped>
.bell {
  position: relative;
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--r-md);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.bell:hover,
.bell[aria-expanded='true'] {
  background: var(--surface-subtle);
  color: var(--text);
}

.bell:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.bell__count {
  position: absolute;
  top: 2px;
  right: 1px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--brand);
  color: #ffffff;
  font-size: 10.5px;
  font-weight: var(--fw-semibold);
  line-height: 17px;
  text-align: center;
}

.feed {
  display: grid;
  gap: var(--space-1);
  width: min(340px, calc(100vw - 32px));
}

.feed__title {
  margin: 0;
  padding: var(--space-2) var(--space-3) var(--space-1);
  font-size: 12px;
  font-weight: var(--fw-semibold);
  color: var(--text-muted);
}

.feed__empty {
  margin: 0;
  padding: var(--space-3);
  font-size: 13px;
  color: var(--text-muted);
}

.feed__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.feed__item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  color: var(--text);
  text-decoration: none;
}

.feed__item:hover,
.feed__item:focus-visible {
  background: var(--surface-subtle);
  outline: none;
  text-decoration: none;
}

.feed__icon {
  flex: none;
  margin-top: 2px;
  color: var(--text-muted);
}

.feed__icon--critical {
  color: var(--text-danger);
}

.feed__icon--warning {
  color: var(--text-warning);
}

.feed__body {
  display: grid;
  gap: 2px;
  min-width: 0;
  font-size: 13px;
}

.feed__body small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-muted);
}

.feed__all {
  margin-top: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--border);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}
</style>
