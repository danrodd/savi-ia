<script setup lang="ts">
/**
 * LoginView — pantalla de inicio de sesión.
 *
 * Si el usuario llegó porque su sesión expiró, el guard pone `next` en
 * el querystring para devolverlo a la vista que quería visitar. Si no
 * hay `next`, vuelve a la home `/`.
 */
import { ref } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { AuthRequestError } from '../services/authService'
import { useAuthStore } from '../stores/authStore'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const login = ref('')
const password = ref('')
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

async function onSubmit(): Promise<void> {
  errorMessage.value = null
  if (!login.value.trim() || !password.value) {
    errorMessage.value = 'Ingresa usuario y contraseña.'
    return
  }
  isSubmitting.value = true
  try {
    await authStore.login({ login: login.value.trim(), password: password.value })
    const next = (route.query.next as string | undefined) ?? '/'
    await router.replace(next)
  } catch (err) {
    if (err instanceof AuthRequestError) {
      errorMessage.value = err.message
    } else if (err instanceof Error) {
      errorMessage.value = err.message
    } else {
      errorMessage.value = 'No se pudo iniciar sesión.'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login__card">
      <div class="login__brand">
        <img
          class="login__logo"
          src="/savi-logo.png"
          alt="SAVI — Asistente Virtual Inteligente"
          width="200"
          height="159"
        >
        <p class="login__subtitle">
          Asistente del ERP de SEO Group
        </p>
      </div>
      <form class="login__form" @submit.prevent="onSubmit">
        <label class="login__field">
          <span class="login__label">Usuario</span>
          <input
            v-model="login"
            class="login__input"
            type="text"
            autocomplete="username"
            autofocus
            :disabled="isSubmitting"
            placeholder="Tu código de usuario"
          />
        </label>
        <label class="login__field">
          <span class="login__label">Contraseña</span>
          <input
            v-model="password"
            class="login__input"
            type="password"
            autocomplete="current-password"
            :disabled="isSubmitting"
            placeholder="••••••••"
          />
        </label>
        <p v-if="errorMessage" class="login__error" role="alert">
          {{ errorMessage }}
        </p>
        <Button type="submit" :loading="isSubmitting" full-width>
          Entrar
        </Button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--bg);
  padding: var(--space-6);
}

.login__card {
  width: min(420px, 100%);
  padding: var(--space-8) var(--space-7);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-md);
}

.login__brand {
  text-align: center;
  margin-bottom: var(--space-7);
}

.login__logo {
  width: 200px;
  height: auto;
  border-radius: var(--r-md);
  margin: 0 0 var(--space-3) 0;
}

.login__subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.login__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.login__label {
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.login__input {
  height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font-family: inherit;
  font-size: 14px;
  transition: border-color var(--duration-fast) var(--ease-out);
}

.login__input:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-ring);
}

.login__input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 13px;
}
</style>
