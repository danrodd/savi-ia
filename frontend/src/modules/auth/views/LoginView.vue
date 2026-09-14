<script setup lang="ts">
/**
 * LoginView — pantalla de inicio de sesión.
 *
 * Si el usuario llegó porque su sesión expiró, el guard pone `next` en
 * el querystring para devolverlo a la vista que quería visitar. Si no
 * hay `next`, vuelve a la home `/`.
 */
import { computed, ref } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { AuthRequestError } from '../services/authService'
import { useAuthStore } from '../stores/authStore'
import {
  loginSuggestions,
  readRememberedCodes,
  rememberCodeFromLogin,
} from '../utils/loginDatabaseCodes'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const login = ref('')
const password = ref('')
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

const rememberedCodes = readRememberedCodes()
const suggestions = computed(() => loginSuggestions(login.value, rememberedCodes))

async function onSubmit(): Promise<void> {
  errorMessage.value = null
  if (!login.value.trim() || !password.value) {
    errorMessage.value = 'Ingresa usuario y contraseña.'
    return
  }
  isSubmitting.value = true
  try {
    await authStore.login({ login: login.value.trim(), password: password.value })
    rememberCodeFromLogin(login.value)
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
    <div class="login__glow login__glow--top" aria-hidden="true" />
    <div class="login__glow login__glow--bottom" aria-hidden="true" />
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
            :aria-invalid="errorMessage ? 'true' : undefined"
            :aria-describedby="errorMessage ? 'login-error' : (rememberedCodes.length === 0 ? 'login-code-hint' : undefined)"
            placeholder="Tu código de usuario"
            list="login-suggestions"
          />
          <datalist id="login-suggestions">
            <option v-for="s in suggestions" :key="s" :value="s" />
          </datalist>
        </label>
        <p v-if="rememberedCodes.length === 0" id="login-code-hint" class="login__hint">
          Si atiendes varios clientes, agrega su código: <code>USUARIO@CODIGO</code>.
        </p>
        <label class="login__field">
          <span class="login__label">Contraseña</span>
          <input
            v-model="password"
            class="login__input"
            type="password"
            autocomplete="current-password"
            :disabled="isSubmitting"
            :aria-invalid="errorMessage ? 'true' : undefined"
            :aria-describedby="errorMessage ? 'login-error' : undefined"
            placeholder="••••••••"
          />
        </label>
        <p v-if="errorMessage" id="login-error" class="login__error" role="alert">
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
  position: relative;
  isolation: isolate;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--surface);
  padding: var(--space-6);
  overflow: hidden;
}

.login__glow {
  position: absolute;
  z-index: -1;
  width: 42vw;
  height: 42vw;
  max-width: 560px;
  max-height: 560px;
  border-radius: 50%;
  background: var(--brand-soft);
  filter: blur(4px);
  opacity: 0.8;
}

.login__glow--top { top: -24%; right: -12%; }
.login__glow--bottom { bottom: -30%; left: -15%; background: var(--navy-soft); }

.login::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background-image: linear-gradient(rgba(128, 128, 128, 0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(128, 128, 128, 0.06) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: linear-gradient(to bottom, black, transparent 75%);
}

.login__card {
  width: min(420px, 100%);
  padding: clamp(var(--space-7), 6vw, var(--space-9)) clamp(var(--space-6), 6vw, var(--space-8));
  background: color-mix(in srgb, var(--surface-elev) 92%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(14px);
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
  box-shadow: var(--focus-ring);
}

.login__input::placeholder { color: var(--text-subtle); }

.login__input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger);
  color: var(--danger);
  font-size: 13px;
  border-left: 3px solid var(--danger);
}

.login__hint {
  margin: calc(-1 * var(--space-2)) 0 0;
  font-size: 12px;
  color: var(--text-subtle);
  line-height: 1.4;
}

.login__hint code {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}

@media (max-width: 600px) {
  .login { padding: var(--space-4); }
  .login__card { border-radius: var(--r-xl); }
}
</style>
