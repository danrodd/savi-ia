<script setup lang="ts">
import QRCode from 'qrcode'
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errorMessage } from '@/lib/useAsync'
import { type AuthStep, useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const step = ref<AuthStep>({ kind: 'credentials' })
const email = ref('')
const password = ref('')
const code = ref('')
const newPassword = ref('')
const repeatPassword = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const qr = ref<string | null>(null)

watch(step, async (value) => {
  qr.value = value.kind === 'setup' ? await QRCode.toDataURL(value.setup.otpauth_uri) : null
})

function destination(): string {
  const next = route.query.next
  return typeof next === 'string' && next.startsWith('/') ? next : '/'
}

async function run(action: () => Promise<void>): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await action()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

function submitCredentials(): Promise<void> {
  return run(async () => {
    step.value = await auth.submitCredentials(email.value, password.value)
    password.value = ''
  })
}

function submitCode(): Promise<void> {
  const current = step.value
  if (current.kind === 'credentials') return Promise.resolve()
  return run(async () => {
    if (current.kind === 'mfa') {
      await auth.submitMfa(current.token, code.value)
    } else {
      if (current.mustChangePassword && newPassword.value !== repeatPassword.value) {
        throw new Error('Las contraseñas no coinciden.')
      }
      await auth.confirmSetup(
        current.token,
        code.value,
        current.mustChangePassword ? newPassword.value : null,
      )
    }
    await router.replace(destination())
  })
}

function back(): void {
  step.value = { kind: 'credentials' }
  code.value = ''
  error.value = null
}
</script>

<template>
  <div class="login">
    <div class="card panel">
      <h1>SAVI <span class="accent">Cloud</span></h1>

      <form v-if="step.kind === 'credentials'" class="stack" @submit.prevent="submitCredentials">
        <p class="muted">Ingresá con tu cuenta del equipo.</p>
        <label>
          Correo
          <input v-model="email" type="email" autocomplete="username" required autofocus />
        </label>
        <label>
          Contraseña
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="error" class="error-text" role="alert">{{ error }}</p>
        <button class="btn btn-primary" type="submit" :disabled="busy">Continuar</button>
      </form>

      <form v-else-if="step.kind === 'mfa'" class="stack" @submit.prevent="submitCode">
        <p class="muted">Ingresá el código de 6 dígitos de tu aplicación de autenticación.</p>
        <label>
          Código
          <input
            v-model="code"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            required
            autofocus
          />
        </label>
        <p v-if="error" class="error-text" role="alert">{{ error }}</p>
        <div class="row">
          <button class="btn" type="button" @click="back">Volver</button>
          <button class="btn btn-primary" type="submit" :disabled="busy">Ingresar</button>
        </div>
      </form>

      <form v-else class="stack" @submit.prevent="submitCode">
        <p>
          <strong>Primer ingreso.</strong> Configurá la verificación en dos pasos: es obligatoria y
          no se puede omitir.
        </p>
        <ol class="steps">
          <li>Escaneá el código con tu aplicación de autenticación.</li>
          <li>Ingresá el código de 6 dígitos que muestra.</li>
        </ol>
        <img v-if="qr" :src="qr" alt="Código QR para la aplicación de autenticación" class="qr" />
        <details>
          <summary>No puedo escanear</summary>
          <p class="muted">Cargá esta clave a mano:</p>
          <code>{{ step.setup.secret }}</code>
        </details>
        <label>
          Código
          <input
            v-model="code"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            required
          />
        </label>
        <template v-if="step.mustChangePassword">
          <label>
            Contraseña nueva (mínimo 12 caracteres)
            <input v-model="newPassword" type="password" autocomplete="new-password" required />
          </label>
          <label>
            Repetí la contraseña
            <input v-model="repeatPassword" type="password" autocomplete="new-password" required />
          </label>
        </template>
        <p v-if="error" class="error-text" role="alert">{{ error }}</p>
        <div class="row">
          <button class="btn" type="button" @click="back">Cancelar</button>
          <button class="btn btn-primary" type="submit" :disabled="busy">Activar e ingresar</button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 1rem;
}
.panel {
  display: grid;
  gap: 1rem;
  width: min(420px, 100%);
}
.accent {
  color: var(--accent);
}
.steps {
  margin: 0;
  padding-left: 1.2rem;
  color: var(--text-muted);
}
.qr {
  width: 180px;
  height: 180px;
  justify-self: center;
  background: #fff;
  padding: 6px;
  border-radius: 8px;
}
</style>
