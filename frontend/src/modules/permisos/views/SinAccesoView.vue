<script setup lang="ts">
/**
 * Vista de "sin acceso" — destino del guard cuando el usuario está
 * autenticado pero no tiene el módulo requerido por la ruta.
 *
 * NO redirige al login: la sesión es válida. Le explica al usuario qué
 * pasó y le da una salida (volver al home).
 */
import { computed } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { MODULE_LABELS, type ModuleCode } from '../constants'

const route = useRoute()
const router = useRouter()

const requiredModule = computed<string | null>(() => {
  const raw = route.query.modulo
  return typeof raw === 'string' ? raw : null
})

const requiredLabel = computed<string | null>(() => {
  const code = requiredModule.value
  if (!code) return null
  return MODULE_LABELS[code as ModuleCode] ?? code
})

function goHome(): void {
  void router.push({ name: 'home' })
}
</script>

<template>
  <div class="no-access">
    <div class="no-access__card">
      <div class="no-access__icon" aria-hidden="true">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      </div>
      <h1 class="no-access__title">Sin acceso</h1>
      <p v-if="requiredLabel" class="no-access__msg">
        Esta sección requiere acceso al módulo <strong>{{ requiredLabel }}</strong>,
        que no está habilitado para tu usuario.
      </p>
      <p v-else class="no-access__msg">
        Tu usuario no tiene acceso a esta sección.
      </p>
      <p class="no-access__hint">
        Si necesitás acceso, contactá al administrador del ERP.
      </p>
      <div class="no-access__actions">
        <Button @click="goHome">Volver al inicio</Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-access {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--bg);
  padding: var(--space-6);
}

.no-access__card {
  width: min(480px, 100%);
  padding: var(--space-7);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-md);
  text-align: center;
}

.no-access__icon {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  margin: 0 auto var(--space-4);
  background: var(--surface-subtle);
  color: var(--text-muted);
  border-radius: 50%;
}

.no-access__title {
  margin: 0 0 var(--space-2);
  font-size: 22px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.no-access__msg {
  margin: 0 0 var(--space-2);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}

.no-access__hint {
  margin: 0 0 var(--space-6);
  color: var(--text-muted);
  font-size: 12px;
}

.no-access__actions {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
}
</style>
