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

import AppVersion from '@/components/AppVersion.vue'
import Button from '@/components/ui/Button.vue'
import MfaPanel from '../components/MfaPanel.vue'
import { useAuthStore } from '../stores/authStore'
import type { MfaChallenge } from '../types'
import {
  loginSuggestions,
  readRememberedCodes,
  rememberCodeFromLogin,
} from '../utils/loginDatabaseCodes'
import { loginErrorMessage, MISSING_CREDENTIALS_MESSAGE } from '../utils/loginErrors'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const login = ref('')
const password = ref('')
const showPassword = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

// Segundo factor: si el login devolvió un desafío, se muestra el panel del código en lugar
// del formulario. La contraseña ya se verificó y se descarta de memoria.
const challenge = ref<MfaChallenge | null>(null)

const rememberedCodes = readRememberedCodes()
const suggestions = computed(() => loginSuggestions(login.value, rememberedCodes))

async function enter(): Promise<void> {
  const next = (route.query.next as string | undefined) ?? '/'
  await router.replace(next)
}

function onMfaCancel(message?: string): void {
  challenge.value = null
  password.value = ''
  errorMessage.value = message ?? null
}

async function onSubmit(): Promise<void> {
  errorMessage.value = null
  if (!login.value.trim() || !password.value) {
    errorMessage.value = MISSING_CREDENTIALS_MESSAGE
    return
  }
  isSubmitting.value = true
  try {
    const pending = await authStore.login({
      login: login.value.trim(),
      password: password.value,
    })
    rememberCodeFromLogin(login.value)
    if (pending) {
      challenge.value = pending
      password.value = ''
      return
    }
    await enter()
  } catch (err) {
    errorMessage.value = loginErrorMessage(err)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="login">
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
      <MfaPanel
        v-if="challenge"
        :challenge="challenge"
        @done="enter"
        @cancel="onMfaCancel"
      />
      <form v-else class="login__form" @submit.prevent="onSubmit">
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
          Si atendés varios clientes, agregá su código: <code>USUARIO@CODIGO</code>
        </p>
        <div class="login__field">
          <label class="login__label" for="login-password">Contraseña</label>
          <span class="login__password">
            <input
              id="login-password"
              v-model="password"
              class="login__input login__input--password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              :disabled="isSubmitting"
              :aria-invalid="errorMessage ? 'true' : undefined"
              :aria-describedby="errorMessage ? 'login-error' : undefined"
              placeholder="••••••••"
            />
            <button
              type="button"
              class="login__eye"
              :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'"
              :aria-pressed="showPassword"
              :title="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'"
              @click="showPassword = !showPassword"
            >
              <svg v-if="!showPassword" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M9.9 4.24A9.1 9.1 0 0 1 12 4c6.5 0 10 8 10 8a17.6 17.6 0 0 1-3.2 4.4M6.6 6.6A17.7 17.7 0 0 0 2 12s3.5 8 10 8a9.7 9.7 0 0 0 5.4-1.6" />
                <path d="M14.1 14.1a3 3 0 1 1-4.2-4.2" />
                <path d="m2 2 20 20" />
              </svg>
            </button>
          </span>
        </div>
        <p v-if="errorMessage" id="login-error" class="login__error" role="alert">
          {{ errorMessage }}
        </p>
        <Button type="submit" :loading="isSubmitting" full-width>
          Entrar
        </Button>
      </form>
      <!-- Visible antes de iniciar sesión: quien no puede entrar es
           justamente quien llama a soporte. -->
      <AppVersion class="login__version" />
    </div>
  </main>
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

.login__password {
  position: relative;
  display: flex;
}

.login__input--password {
  flex: 1;
  min-width: 0;
  padding-right: 42px;
}

.login__eye {
  position: absolute;
  top: 50%;
  right: 4px;
  transform: translateY(-50%);
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
}

.login__eye:hover { background: var(--surface-subtle); color: var(--text); }
.login__eye:focus-visible { outline: 2px solid var(--brand); outline-offset: 1px; }

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

.login__version {
  margin-top: var(--space-6);
  text-align: center;
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
