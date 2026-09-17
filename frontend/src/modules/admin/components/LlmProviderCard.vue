<script setup lang="ts">
import {
  CircleCheck,
  CircleDashed,
  Clock,
  FlaskConical,
  KeyRound,
  MessageSquare,
  Settings2,
  TriangleAlert,
  Type,
} from 'lucide-vue-next'
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'
import type { LlmProvider } from '../types'
import ProviderIcon from './ProviderIcon.vue'

const props = defineProps<{
  provider: LlmProvider
  canActivate: boolean
  activateReason?: string
}>()
const emit = defineEmits<{ configure: []; activate: [] }>()

const status = computed(() => {
  const p = props.provider
  if (p.is_active) return { label: 'Activo', icon: CircleCheck, tone: 'active' }
  if (p.credentials_unreadable) {
    return { label: 'Credencial ilegible', icon: TriangleAlert, tone: 'warning' }
  }
  if (p.configured) return { label: 'Configurado', icon: Settings2, tone: 'neutral' }
  if (p.implemented) return { label: 'Sin configurar', icon: CircleDashed, tone: 'neutral' }
  return { label: 'Próximamente', icon: Clock, tone: 'neutral' }
})
</script>

<template>
  <article class="provider-card">
    <header class="provider-card__header">
      <div class="provider-card__identity">
        <ProviderIcon :kind="provider.provider" :size="24" />
        <div class="provider-card__identity-text">
          <h2>{{ provider.display_name }}</h2>
          <span class="provider-card__kind">{{ provider.provider }}</span>
        </div>
      </div>
      <span class="status" :class="`status--${status.tone}`">
        <component :is="status.icon" :size="13" aria-hidden="true" />
        {{ status.label }}
      </span>
    </header>
    <p v-if="!provider.implemented" class="provider-card__muted">Este proveedor aún no está disponible.</p>
    <div v-else class="provider-card__body">
      <div class="provider-card__group">
        <span class="provider-card__group-label">Modelos</span>
        <div class="provider-card__model-row">
          <span class="provider-card__model-tag"><MessageSquare :size="12" aria-hidden="true" /> Chat</span>
          <code class="provider-card__model-id">{{ provider.chat_model ?? 'No definido' }}</code>
        </div>
        <div class="provider-card__model-row">
          <span class="provider-card__model-tag"><Type :size="12" aria-hidden="true" /> Títulos</span>
          <code class="provider-card__model-id">{{ provider.title_model ?? 'No definido' }}</code>
        </div>
      </div>
      <div class="provider-card__status-row">
        <span
          class="provider-card__status-item"
          :class="{ 'provider-card__status-item--warning': !provider.has_credential }"
        >
          <KeyRound :size="13" aria-hidden="true" />
          {{ provider.has_credential ? 'Credencial guardada' : 'Falta configurar credencial' }}
        </span>
        <span class="provider-card__status-item">
          <FlaskConical :size="13" aria-hidden="true" />
          {{
            provider.last_test_ok_at
              ? `Probado el ${new Date(provider.last_test_ok_at).toLocaleString()}`
              : 'Sin probar'
          }}
        </span>
      </div>
    </div>
    <p v-if="provider.is_active && provider.chat_model && !provider.pricing[provider.chat_model]" class="provider-card__price-warning">
      El costo de las respuestas no se va a registrar hasta cargar el precio de este modelo.
    </p>
    <footer class="provider-card__actions">
      <Button variant="secondary" :disabled="!provider.implemented" @click="emit('configure')">{{ provider.configured ? 'Editar' : 'Configurar' }}</Button>
      <span :title="activateReason"><Button :disabled="!canActivate || provider.is_active || !provider.implemented" @click="emit('activate')">Activar</Button></span>
    </footer>
  </article>
</template>

<style scoped>
.provider-card { padding: var(--space-6); background: var(--surface-elev); border: 1px solid var(--border); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); }
.provider-card__header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-3) var(--space-4); }
.provider-card__actions { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); }
.provider-card__identity { display: flex; align-items: center; gap: var(--space-3); min-width: 0; flex: 1 1 auto; }
.provider-card__identity-text { min-width: 0; }
.provider-card__identity h2 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
h2 { margin: 0; font-family: var(--font-display); font-size: 18px; }
.provider-card__kind { color: var(--text-subtle); font-size: 11px; }
.status { display: inline-flex; flex-shrink: 0; align-items: center; gap: var(--space-2); padding: 3px 9px; color: var(--text-muted); background: var(--surface-subtle); border-radius: var(--r-pill); font-size: 11px; font-weight: var(--fw-semibold); white-space: nowrap; }
.status--active { color: var(--success); background: var(--success-soft); }
.status--warning { color: var(--warning); }
.provider-card__body { margin: var(--space-6) 0; }
.provider-card__group-label { display: block; margin-bottom: var(--space-3); color: var(--text-subtle); font-size: 10px; font-weight: var(--fw-semibold); text-transform: uppercase; letter-spacing: .06em; }
.provider-card__model-row { display: flex; align-items: center; gap: var(--space-3); }
.provider-card__model-row + .provider-card__model-row { margin-top: var(--space-2); }
.provider-card__model-tag { display: inline-flex; flex-shrink: 0; align-items: center; gap: var(--space-2); width: 62px; color: var(--text-muted); font-size: 12px; }
.provider-card__model-id { overflow: hidden; padding: 2px 8px; color: var(--text); background: var(--surface-subtle); border-radius: var(--r-sm); font-family: var(--font-mono); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.provider-card__status-row { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-4); padding-top: var(--space-4); border-top: 1px solid var(--border); }
.provider-card__status-item { display: inline-flex; align-items: center; gap: var(--space-2); color: var(--text-muted); font-size: 12px; }
.provider-card__status-item--warning { color: var(--warning); font-weight: var(--fw-medium); }
.provider-card__muted, .provider-card__price-warning { margin: var(--space-5) 0; color: var(--text-muted); font-size: 13px; }
.provider-card__price-warning { padding: var(--space-3); color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, transparent); border-radius: var(--r-sm); }
.provider-card__actions { justify-content: flex-end; }
</style>
