<script setup lang="ts">
import {
  Alert,
  Button,
  CopyField,
  OtpInput,
  PasswordField,
  Stepper,
  TextField,
  useZodForm,
} from '@savi/ui'
import { ArrowLeft, ShieldCheck } from 'lucide-vue-next'
import QRCode from 'qrcode'
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/lib/http'
import { credentialsSchema, newPasswordSchema, passwordRules } from '@/lib/schemas/auth'
import type { MfaSetup } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

// Archivo de `public/`: como binding, Vite no intenta resolverlo como import.
const LOGO = '/savi-logo.png'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

/**
 * Pasos del ingreso. En el primer ingreso la contraseña nueva se pide ANTES que el código
 * TOTP y no se envía hasta tener el código: el código vence en 30 segundos y antes se
 * vencía mientras se escribían las contraseñas.
 */
type Step =
  | { kind: 'credentials' }
  | { kind: 'mfa'; token: string }
  | { kind: 'password'; token: string; setup: MfaSetup }
  | { kind: 'setup'; token: string; setup: MfaSetup; mustChangePassword: boolean }

const step = shallowRef<Step>({ kind: 'credentials' })
const notice = ref<string | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const code = ref('')
const qr = ref<string | null>(null)
const otp = ref<InstanceType<typeof OtpInput> | null>(null)

const login = useZodForm(credentialsSchema, { email: '', password: '' })

const email = computed(() => login.values.email.trim())
const rules = computed(() => passwordRules(email.value))
const passwordForm = useZodForm(
  newPasswordSchema(() => email.value),
  {
    password: '',
    repeat: '',
  },
)

/** Primer ingreso con cambio de contraseña: muestra el progreso en tres pasos. */
const firstAccess = computed(
  () =>
    step.value.kind === 'password' ||
    (step.value.kind === 'setup' && step.value.mustChangePassword),
)
const STEPS = [
  { key: 'credentials', label: 'Ingreso' },
  { key: 'password', label: 'Contraseña' },
  { key: 'setup', label: 'Verificación' },
]

watch(step, async (value) => {
  code.value = ''
  error.value = null
  qr.value =
    value.kind === 'setup'
      ? await QRCode.toDataURL(value.setup.otpauth_uri, { margin: 1, width: 200 })
      : null
})

function destination(): string {
  const next = route.query.next
  return typeof next === 'string' && next.startsWith('/') ? next : '/'
}

function backToCredentials(message: string | null = null): void {
  step.value = { kind: 'credentials' }
  notice.value = message
  login.values.password = ''
  passwordForm.reset({ password: '', repeat: '' })
}

async function submitCredentials(): Promise<void> {
  notice.value = null
  error.value = null
  await login.handleSubmit(async ({ email: mail, password }) => {
    busy.value = true
    try {
      const next = await auth.submitCredentials(mail, password)
      login.values.password = ''
      if (next.kind === 'setup' && next.mustChangePassword) {
        step.value = { kind: 'password', token: next.token, setup: next.setup }
      } else if (next.kind !== 'credentials') {
        step.value = next
      }
    } catch (e) {
      error.value = errorMessage(e)
    } finally {
      busy.value = false
    }
  })
}

function confirmPassword(): void {
  const current = step.value
  if (current.kind !== 'password') return
  void passwordForm.handleSubmit(() => {
    step.value = {
      kind: 'setup',
      token: current.token,
      setup: current.setup,
      mustChangePassword: true,
    }
  })
}

function onCodeRejected(e: unknown): void {
  if (e instanceof ApiError && e.code === 'invalid_session_token') {
    backToCredentials('Pasó demasiado tiempo y la verificación venció. Ingresá de nuevo.')
    return
  }
  error.value = errorMessage(e)
  otp.value?.clear()
}

async function submitCode(value: string): Promise<void> {
  const current = step.value
  if (busy.value || (current.kind !== 'mfa' && current.kind !== 'setup')) return
  busy.value = true
  error.value = null
  try {
    if (current.kind === 'mfa') {
      await auth.submitMfa(current.token, value)
    } else {
      await auth.confirmSetup(
        current.token,
        value,
        current.mustChangePassword ? passwordForm.values.password : null,
      )
    }
    await router.replace(destination())
  } catch (e) {
    if (current.kind === 'setup' && e instanceof ApiError && e.code === 'weak_password') {
      // La política del servidor tiene una regla más (contraseñas comunes): se vuelve al
      // paso de la contraseña con su mensaje en el campo, sin perder el resto.
      step.value = { kind: 'password', token: current.token, setup: current.setup }
      await nextTick()
      passwordForm.setServerErrors({ password: e.message })
      return
    }
    onCodeRejected(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login">
    <div class="login__glow login__glow--top" aria-hidden="true" />
    <div class="login__glow login__glow--bottom" aria-hidden="true" />

    <div class="login__card">
      <div class="login__brand">
        <img class="login__logo" :src="LOGO" alt="SAVI" width="150" height="119" />
        <p class="login__product">SAVI <span>Cloud</span></p>
        <p class="login__subtitle">Consola del staff de SEO Group</p>
      </div>

      <Stepper v-if="firstAccess" class="login__stepper" :steps="STEPS" :current="step.kind" />

      <!-- 1. Credenciales -->
      <form
        v-if="step.kind === 'credentials'"
        class="login__form"
        novalidate
        @submit.prevent="submitCredentials"
      >
        <Alert v-if="notice" tone="warning">{{ notice }}</Alert>
        <TextField
          v-model="login.values.email"
          label="Correo"
          type="email"
          autocomplete="username"
          placeholder="nombre@seogroup.com"
          :error="login.errors.value.email"
          :disabled="busy"
          @blur="login.touch('email')"
        />
        <PasswordField
          v-model="login.values.password"
          label="Contraseña"
          autocomplete="current-password"
          :error="login.errors.value.password"
          :disabled="busy"
          @blur="login.touch('password')"
        />
        <Alert v-if="error" tone="danger">{{ error }}</Alert>
        <Button type="submit" size="lg" :loading="busy" full-width>Continuar</Button>
      </form>

      <!-- 2. Nueva contraseña (primer ingreso) -->
      <form
        v-else-if="step.kind === 'password'"
        class="login__form"
        novalidate
        @submit.prevent="confirmPassword"
      >
        <div class="login__intro">
          <h1>Elegí tu contraseña</h1>
          <p>Reemplaza la temporal que te pasaron. La vas a usar en cada ingreso.</p>
        </div>
        <PasswordField
          v-model="passwordForm.values.password"
          label="Contraseña nueva"
          autocomplete="new-password"
          :rules="rules"
          :error="passwordForm.errors.value.password"
          @blur="passwordForm.touch('password')"
        />
        <PasswordField
          v-model="passwordForm.values.repeat"
          label="Repetí la contraseña"
          autocomplete="new-password"
          :error="passwordForm.errors.value.repeat"
          @blur="passwordForm.touch('repeat')"
        />
        <Button type="submit" size="lg" full-width data-test="password-continue">
          Continuar con la verificación
        </Button>
        <button type="button" class="login__back" @click="backToCredentials()">
          <ArrowLeft :size="14" aria-hidden="true" /> Volver al ingreso
        </button>
      </form>

      <!-- 3. Configurar el segundo factor -->
      <div v-else-if="step.kind === 'setup'" class="login__form">
        <div class="login__intro">
          <h1><ShieldCheck :size="18" aria-hidden="true" /> Verificación en dos pasos</h1>
          <p>Es obligatoria para entrar a la consola. Te lleva un minuto.</p>
        </div>
        <ol class="login__steps">
          <li>Abrí tu aplicación de autenticación (Google Authenticator, Microsoft Authenticator…).</li>
          <li>Escaneá este código, o cargá la clave a mano.</li>
          <li>Escribí el código de 6 dígitos que muestra la aplicación.</li>
        </ol>
        <div class="login__qr">
          <img v-if="qr" :src="qr" alt="Código QR para la aplicación de autenticación" width="168" height="168" />
        </div>
        <CopyField :value="step.setup.secret" label="Clave para cargar a mano" />
        <OtpInput
          ref="otp"
          v-model="code"
          label="Código de la aplicación"
          :error="error"
          :disabled="busy"
          autofocus
          @complete="submitCode"
        />
        <p class="login__hint" aria-live="polite">
          {{ busy ? 'Verificando…' : 'Se envía solo al completar los 6 dígitos.' }}
        </p>
        <button type="button" class="login__back" :disabled="busy" @click="backToCredentials()">
          <ArrowLeft :size="14" aria-hidden="true" /> Cancelar y volver al ingreso
        </button>
      </div>

      <!-- Ingreso con el segundo factor ya configurado -->
      <div v-else class="login__form">
        <div class="login__intro">
          <h1><ShieldCheck :size="18" aria-hidden="true" /> Código de verificación</h1>
          <p>Escribí el código de 6 dígitos de tu aplicación de autenticación.</p>
        </div>
        <OtpInput
          ref="otp"
          v-model="code"
          label="Código"
          :error="error"
          :disabled="busy"
          autofocus
          @complete="submitCode"
        />
        <p class="login__hint" aria-live="polite">
          {{ busy ? 'Verificando…' : 'Se envía solo al completar los 6 dígitos.' }}
        </p>
        <button type="button" class="login__back" :disabled="busy" @click="backToCredentials()">
          <ArrowLeft :size="14" aria-hidden="true" /> Volver al ingreso
        </button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.login {
  position: relative;
  isolation: isolate;
  /* Sin `place-items: center`: con la tarjeta más alta que la pantalla, el centrado
     recortaba la parte de arriba. El `margin: auto` de la tarjeta centra sin recortar. */
  display: grid;
  height: 100%;
  padding: var(--space-6);
  overflow-y: auto;
  background: var(--surface);
}

.login::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: -1;
  background-image:
    linear-gradient(rgba(128, 128, 128, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(128, 128, 128, 0.06) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: linear-gradient(to bottom, black, transparent 75%);
}

.login__glow {
  position: fixed;
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

.login__glow--top {
  top: -24%;
  right: -12%;
}

.login__glow--bottom {
  bottom: -30%;
  left: -15%;
  background: var(--navy-soft);
}

.login__card {
  width: min(440px, 100%);
  margin: auto;
  padding: clamp(var(--space-7), 6vw, var(--space-8)) clamp(var(--space-6), 6vw, var(--space-8));
  background: color-mix(in srgb, var(--surface-elev) 92%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(14px);
}

.login__brand {
  margin-bottom: var(--space-7);
  text-align: center;
}

.login__logo {
  width: 150px;
  height: auto;
  margin: 0 0 var(--space-3);
  border-radius: var(--r-md);
}

.login__product {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
  letter-spacing: 0.02em;
}

.login__product span {
  color: var(--brand);
}

.login__subtitle {
  margin: var(--space-1) 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

.login__stepper {
  margin-bottom: var(--space-6);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.login__intro {
  display: grid;
  gap: var(--space-1);
}

.login__intro h1 {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: var(--fw-semibold);
}

.login__intro p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.login__steps {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding-left: var(--space-6);
  font-size: 13px;
  color: var(--text-muted);
}

.login__qr {
  display: grid;
  place-items: center;
  min-height: 184px;
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: #ffffff;
}

.login__hint {
  margin: calc(-1 * var(--space-3)) 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.login__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 32px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.login__back:hover:not(:disabled) {
  color: var(--text);
}

.login__back:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 600px) {
  .login {
    padding: var(--space-4);
  }
}
</style>
