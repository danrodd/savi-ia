<script setup lang="ts">
/**
 * UserProfileView — datos del usuario autenticado.
 *
 * Hidrata desde el store (sin re-pegarle al backend en el render). Si por
 * algún motivo el store no tiene el `user` (ej. el usuario manipuló
 * localStorage), refresca con `fetchMe()` que llama a /auth/me — y si
 * eso devuelve 401 limpia sesión y redirige a /login (lo hace el
 * HttpClient interceptor → store → bridge).
 */
import { computed, onMounted, ref } from 'vue'

import { useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { useAuthStore } from '../stores/authStore'

const authStore = useAuthStore()
const router = useRouter()

const refreshing = ref(false)
const refreshError = ref<string | null>(null)
const loggingOut = ref(false)

const user = computed(() => authStore.user)

const initial = computed(() => {
  const name = user.value?.full_name ?? user.value?.login ?? ''
  return name.trim().charAt(0).toUpperCase() || 'U'
})

const roleLabel = computed(() => (user.value?.is_admin ? 'Administrador' : 'Usuario'))

async function onRefresh(): Promise<void> {
  refreshing.value = true
  refreshError.value = null
  try {
    await authStore.fetchMe()
  } catch (e) {
    refreshError.value = (e as Error).message || 'No se pudo refrescar la información.'
  } finally {
    refreshing.value = false
  }
}

async function onLogout(): Promise<void> {
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    loggingOut.value = false
    void router.push({ name: 'login' })
  }
}

function goBack(): void {
  // Vuelve a la conversación que estaba abierta. Si no hay history,
  // cae a home.
  if (window.history.length > 1) router.back()
  else void router.push({ name: 'home' })
}

onMounted(() => {
  // Refresca silenciosamente en cada montaje — barato, mantiene los
  // datos actualizados si cambian en el ERP.
  if (authStore.user) void authStore.fetchMe().catch(() => undefined)
})
</script>

<template>
  <div class="profile">
    <div class="profile__card">
      <button type="button" class="profile__back" aria-label="Volver" @click="goBack">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Volver
      </button>

      <div v-if="user" class="profile__body">
        <div class="profile__avatar" aria-hidden="true">{{ initial }}</div>
        <h1 class="profile__name">{{ user.full_name }}</h1>
        <span class="profile__role" :class="{ 'profile__role--admin': user.is_admin }">
          {{ roleLabel }}
        </span>

        <dl class="profile__facts">
          <div class="profile__fact">
            <dt class="profile__fact-label">Usuario</dt>
            <dd class="profile__fact-value profile__fact-value--mono">{{ user.login }}</dd>
          </div>
          <div class="profile__fact">
            <dt class="profile__fact-label">ID</dt>
            <dd class="profile__fact-value profile__fact-value--mono">#{{ user.id }}</dd>
          </div>
          <div class="profile__fact">
            <dt class="profile__fact-label">Origen de identidad</dt>
            <dd class="profile__fact-value">Seguridad.Usuario (ERP)</dd>
          </div>
        </dl>

        <p v-if="refreshError" class="profile__error" role="alert">{{ refreshError }}</p>

        <div class="profile__actions">
          <Button variant="secondary" :loading="refreshing" @click="onRefresh">
            Refrescar datos
          </Button>
          <Button variant="ghost" :loading="loggingOut" @click="onLogout">
            Cerrar sesión
          </Button>
        </div>
      </div>

      <div v-else class="profile__empty">
        <p>No hay información de usuario disponible.</p>
        <Button @click="() => router.push({ name: 'login' })">Ir al login</Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--bg);
  padding: var(--space-6);
}

.profile__card {
  width: min(520px, 100%);
  padding: var(--space-7);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-md);
  position: relative;
}

.profile__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  margin-bottom: var(--space-5);
}

.profile__back:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.profile__body {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.profile__avatar {
  width: 80px;
  height: 80px;
  display: grid;
  place-items: center;
  background: var(--brand);
  color: var(--text-on-brand);
  border-radius: 50%;
  font-size: 32px;
  font-weight: var(--fw-semibold);
  box-shadow: var(--shadow-md);
  margin-bottom: var(--space-4);
}

.profile__name {
  margin: 0 0 var(--space-2) 0;
  font-family: var(--font-display, var(--font-sans));
  font-size: 22px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
  text-align: center;
}

.profile__role {
  display: inline-block;
  padding: 4px var(--space-3);
  border-radius: 999px;
  font-size: 11px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: var(--surface-subtle);
  color: var(--text-muted);
  margin-bottom: var(--space-6);
}

.profile__role--admin {
  background: var(--brand);
  color: var(--text-on-brand);
}

.profile__facts {
  width: 100%;
  margin: 0 0 var(--space-6) 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow: hidden;
}

.profile__fact {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  margin: 0;
  background: var(--surface-elev);
}

.profile__fact-label {
  margin: 0;
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.profile__fact-value {
  margin: 0;
  font-size: 13px;
  color: var(--text);
  text-align: right;
}

.profile__fact-value--mono {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  letter-spacing: 0.02em;
}

.profile__error {
  margin: 0 0 var(--space-4) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
  width: 100%;
}

.profile__actions {
  display: flex;
  gap: var(--space-3);
  width: 100%;
  justify-content: center;
  flex-wrap: wrap;
}

.profile__empty {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-6) 0;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
