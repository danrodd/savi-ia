<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import type { LlmProvider } from '../types'

defineProps<{ provider: LlmProvider; canActivate: boolean; activateReason?: string }>()
const emit = defineEmits<{ configure: []; activate: [] }>()
</script>

<template>
  <article class="provider-card">
    <header class="provider-card__header">
      <div><h2>{{ provider.display_name }}</h2><span class="provider-card__kind">{{ provider.provider }}</span></div>
      <span class="status" :class="{ 'status--active': provider.is_active, 'status--warning': provider.credentials_unreadable }">
        {{ provider.is_active ? 'Activo' : provider.credentials_unreadable ? 'Credencial ilegible' : provider.configured ? 'Configurado' : provider.implemented ? 'Sin configurar' : 'Próximamente' }}
      </span>
    </header>
    <p v-if="!provider.implemented" class="provider-card__muted">Este proveedor aún no está disponible.</p>
    <dl v-else class="provider-card__summary">
      <div><dt>Modelo de chat</dt><dd>{{ provider.chat_model ?? 'No definido' }}</dd></div>
      <div><dt>Modelo de títulos</dt><dd>{{ provider.title_model ?? 'No definido' }}</dd></div>
      <div><dt>Última prueba</dt><dd>{{ provider.last_test_ok_at ? new Date(provider.last_test_ok_at).toLocaleString() : 'Sin probar' }}</dd></div>
      <div><dt>Credencial</dt><dd>{{ provider.has_credential ? 'Guardada' : 'Falta configurar' }}</dd></div>
    </dl>
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
.provider-card__header, .provider-card__actions { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); }
h2 { margin: 0; font-family: var(--font-display); font-size: 18px; }
.provider-card__kind { color: var(--text-subtle); font-size: 11px; }
.status { padding: 3px 9px; color: var(--text-muted); background: var(--surface-subtle); border-radius: var(--r-pill); font-size: 11px; font-weight: var(--fw-semibold); }
.status--active { color: var(--success); background: var(--success-soft); }.status--warning { color: var(--warning); }
.provider-card__summary { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-4); margin: var(--space-6) 0; }
.provider-card__muted, .provider-card__price-warning { margin: var(--space-5) 0; color: var(--text-muted); font-size: 13px; }.provider-card__price-warning { padding: var(--space-3); color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, transparent); border-radius: var(--r-sm); }
.provider-card__actions { justify-content: flex-end; }
@media (max-width: 540px) { .provider-card__summary { grid-template-columns: 1fr; } }
</style>
