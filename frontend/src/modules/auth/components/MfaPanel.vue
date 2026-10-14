<script setup lang="ts">
/**
 * MfaPanel — segundo paso del inicio de sesión.
 *
 * Dos modos según el desafío que devolvió el login:
 * - `mfa_required`: ya tiene la aplicación configurada, pide el código de 6 dígitos.
 * - `mfa_setup_required`: primer ingreso. Muestra el QR (y la clave para cargar a mano) y pide
 *   el primer código para activar el segundo factor.
 *
 * El QR codifica la URI `otpauth://` con el secreto. El texto de la clave es el mismo dato en
 * otra forma, para quien no puede escanear.
 */

import QRCode from 'qrcode'
import { computed, onMounted, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import { useAuthStore } from '../stores/authStore'
import type { MfaChallenge, MfaSetup } from '../types'
import { isMfaExpired, loginErrorMessage, MFA_EXPIRED_MESSAGE } from '../utils/loginErrors'

const props = defineProps<{ challenge: MfaChallenge }>()
const emit = defineEmits<{
  /** La sesión quedó abierta. */
  done: []
  /** Volver al formulario de usuario y contraseña (con un aviso opcional). */
  cancel: [message?: string]
}>()

const authStore = useAuthStore()

const isSetup = computed(() => props.challenge.status === 'mfa_setup_required')
const setup = ref<MfaSetup | null>(null)
const qr = ref<string | null>(null)
const code = ref('')
const busy = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

async function loadSetup(): Promise<void> {
  loading.value = true
  try {
    const data = await authStore.beginMfaSetup(props.challenge.mfa_token)
    setup.value = data
    qr.value = await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 192 })
  } catch (e) {
    handleFailure(e)
  } finally {
    loading.value = false
  }
}

function handleFailure(e: unknown): void {
  if (isMfaExpired(e)) {
    emit('cancel', MFA_EXPIRED_MESSAGE)
    return
  }
  error.value = loginErrorMessage(e)
}

async function onSubmit(): Promise<void> {
  error.value = null
  const clean = code.value.replace(/\s+/g, '')
  if (clean.length < 6) {
    error.value = 'Ingresá los 6 dígitos de tu aplicación.'
    return
  }
  busy.value = true
  try {
    if (isSetup.value) await authStore.confirmMfaSetup(props.challenge.mfa_token, clean)
    else await authStore.verifyMfa(props.challenge.mfa_token, clean)
    emit('done')
  } catch (e) {
    code.value = ''
    handleFailure(e)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  if (isSetup.value) void loadSetup()
})
</script>

<template>
  <form class="mfa" data-testid="mfa-panel" @submit.prevent="onSubmit">
    <template v-if="isSetup">
      <h2 class="mfa__title">Activá la verificación en dos pasos</h2>
      <p class="mfa__text">
        Tu cuenta administra SAVI, así que necesita un segundo paso al entrar. Es una sola vez.
      </p>
      <ol class="mfa__steps">
        <li>Instalá una aplicación de autenticación (Google Authenticator, Microsoft Authenticator o similar).</li>
        <li>Escaneá este código con la aplicación.</li>
        <li>Escribí abajo el código de 6 dígitos que te muestra.</li>
      </ol>
      <p v-if="loading" class="mfa__text" role="status">Preparando el código…</p>
      <img
        v-if="qr"
        :src="qr"
        class="mfa__qr"
        width="192"
        height="192"
        alt="Código QR para la aplicación de autenticación"
        data-testid="mfa-qr"
      >
      <details v-if="setup" class="mfa__manual">
        <summary>No puedo escanear el código</summary>
        <p class="mfa__text">Cargá esta clave a mano en la aplicación:</p>
        <code class="mfa__secret" data-testid="mfa-secret">{{ setup.secret }}</code>
      </details>
    </template>
    <template v-else>
      <h2 class="mfa__title">Verificación en dos pasos</h2>
      <p class="mfa__text">Ingresá el código de 6 dígitos de tu aplicación de autenticación.</p>
    </template>

    <label class="mfa__field">
      <span class="mfa__label">Código</span>
      <input
        v-model="code"
        class="mfa__input"
        type="text"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="8"
        autofocus
        :disabled="busy || (isSetup && !setup)"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="error ? 'mfa-error' : undefined"
        placeholder="000000"
        data-testid="mfa-code"
      >
    </label>

    <p v-if="error" id="mfa-error" class="mfa__error" role="alert">{{ error }}</p>

    <Button type="submit" :loading="busy" full-width>
      {{ isSetup ? 'Activar y entrar' : 'Entrar' }}
    </Button>
    <button type="button" class="mfa__back" @click="emit('cancel')">Volver</button>
  </form>
</template>

<style scoped>
.mfa {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.mfa__title {
  margin: 0;
  font-size: 16px;
  font-weight: var(--fw-semibold, 600);
  color: var(--text);
}

.mfa__text {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.45;
}

.mfa__steps {
  margin: 0;
  padding-left: var(--space-5);
  font-size: 13px;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mfa__qr {
  align-self: center;
  background: #fff;
  padding: var(--space-2);
  border-radius: var(--r-md);
  border: 1px solid var(--border);
}

.mfa__manual {
  font-size: 13px;
  color: var(--text-muted);
}

.mfa__secret {
  display: block;
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-subtle);
  color: var(--text);
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  word-break: break-all;
  user-select: all;
}

.mfa__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mfa__label {
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.mfa__input {
  height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font-family: var(--font-mono, monospace);
  font-size: 20px;
  letter-spacing: 0.3em;
  text-align: center;
}

.mfa__input:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: var(--focus-ring);
}

.mfa__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger);
  color: var(--danger);
  font-size: 13px;
  border-left: 3px solid var(--danger);
}

.mfa__back {
  align-self: center;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  text-decoration: underline;
}
</style>
