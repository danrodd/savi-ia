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

import { TwoFactorPanel } from '@savi/ui'
import QRCode from 'qrcode'
import { computed, onMounted, ref, useTemplateRef } from 'vue'
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
const error = ref<string | null>(null)
const panel = useTemplateRef<InstanceType<typeof TwoFactorPanel>>('panel')

async function loadSetup(): Promise<void> {
  try {
    const data = await authStore.beginMfaSetup(props.challenge.mfa_token)
    setup.value = data
    qr.value = await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 296 })
  } catch (e) {
    handleFailure(e)
  }
}

function handleFailure(e: unknown): void {
  if (isMfaExpired(e)) {
    emit('cancel', MFA_EXPIRED_MESSAGE)
    return
  }
  error.value = loginErrorMessage(e)
}

/** Se llama sola al completar los 6 dígitos: el código vence en segundos. */
async function onComplete(value: string): Promise<void> {
  if (busy.value) return
  error.value = null
  busy.value = true
  try {
    if (isSetup.value) await authStore.confirmMfaSetup(props.challenge.mfa_token, value)
    else await authStore.verifyMfa(props.challenge.mfa_token, value)
    emit('done')
  } catch (e) {
    handleFailure(e)
    panel.value?.clear()
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  if (isSetup.value) void loadSetup()
})
</script>

<template>
  <div data-testid="mfa-panel">
    <TwoFactorPanel
      ref="panel"
      v-model:code="code"
      :mode="isSetup ? 'setup' : 'verify'"
      :qr="qr"
      :secret="setup?.secret ?? null"
      :busy="busy"
      :error="error"
      reason="Su cuenta administra SAVI: además de la contraseña, al entrar se le pedirá un código de su celular. Se configura una sola vez."
      recovery-hint="Pida a otra persona administradora de SAVI que restablezca su verificación en Administración → Seguridad."
      back-label="Volver al ingreso"
      @complete="onComplete"
      @back="emit('cancel')"
    />
  </div>
</template>
