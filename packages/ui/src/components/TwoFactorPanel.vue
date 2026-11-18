<script setup lang="ts">
import { ArrowLeft, Check, Copy, KeyRound, ShieldCheck } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import OtpInput from './OtpInput.vue'

/**
 * Verificación en dos pasos, igual en SAVI y en la consola de Cloud.
 *
 * - `setup`: primer ingreso. Tres pasos cortos (instalar la aplicación, escanear, escribir el
 *   código) con el QR compacto; la clave para cargar a mano queda plegada, agrupada de a cuatro.
 * - `verify`: ingreso habitual. Solo las casillas, cuánto falta para que el código cambie y qué
 *   hacer si no tiene el celular.
 *
 * Es presentacional: el padre arma el QR, llama al servidor y decide qué pasa después.
 */
const props = withDefaults(
  defineProps<{
    mode: 'setup' | 'verify'
    /** QR como data URL. `null` mientras se prepara. */
    qr?: string | null
    /** Clave en Base32 para cargar a mano (solo `setup`). */
    secret?: string | null
    busy?: boolean
    error?: string | null
    /** Por qué se pide (primer ingreso). */
    reason?: string
    /** Qué hacer si perdió el celular (ingreso habitual). */
    recoveryHint?: string
    backLabel?: string
  }>(),
  {
    qr: null,
    secret: null,
    reason:
      'Además de la contraseña, al entrar se le pedirá un código de su celular. Se configura una sola vez.',
    recoveryHint: 'Pida a un administrador que restablezca su verificación en dos pasos.',
    backLabel: 'Volver al ingreso',
  },
)

const code = defineModel<string>('code', { default: '' })
const emit = defineEmits<{ complete: [code: string]; back: [] }>()

const otp = useTemplateRef<InstanceType<typeof OtpInput>>('otp')
defineExpose({ clear: () => otp.value?.clear(), focus: () => otp.value?.focus() })

// Las casillas están deshabilitadas hasta que llega el QR: al llegar, el foco va a la primera.
watch(
  () => props.qr,
  (value, previous) => {
    if (value && !previous) void nextTick(() => otp.value?.focus())
  },
)

// ── Clave a mano ──────────────────────────────────────────────
const showKey = ref(false)
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | undefined

/** "JBSWY3DPEHPK3PXP" → "JBSW Y3DP EHPK 3PXP": se dicta y se compara sin perderse. */
const groupedSecret = computed(() => (props.secret ?? '').replace(/(.{4})/g, '$1 ').trim())

async function copySecret(): Promise<void> {
  if (!props.secret) return
  try {
    // Se copia sin espacios: algunas aplicaciones no los aceptan.
    await navigator.clipboard.writeText(props.secret)
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    showKey.value = true
  }
}

// ── Cuenta regresiva del código ───────────────────────────────
// Los códigos TOTP cambian cada 30 s alineados al reloj: la aplicación y esta cuenta coinciden.
const PERIOD = 30
const remaining = ref(PERIOD)
let tick: ReturnType<typeof setInterval> | undefined

function update(): void {
  remaining.value = PERIOD - (Math.floor(Date.now() / 1000) % PERIOD)
}

onMounted(() => {
  update()
  tick = setInterval(update, 1000)
})

onBeforeUnmount(() => {
  clearInterval(tick)
  clearTimeout(copiedTimer)
})

const RING = 2 * Math.PI * 9
const ringOffset = computed(() => RING * (1 - remaining.value / PERIOD))

const status = computed(() => {
  if (props.busy) return 'Verificando…'
  return 'Se envía solo al completar los 6 dígitos.'
})
</script>

<template>
  <div class="ui-2fa" :data-mode="mode" data-test="two-factor">
    <header class="ui-2fa__head">
      <span class="ui-2fa__badge" aria-hidden="true"><ShieldCheck :size="20" /></span>
      <div>
        <h1 class="ui-2fa__title">
          {{ mode === 'setup' ? 'Proteja su cuenta' : 'Código de verificación' }}
        </h1>
        <p class="ui-2fa__lead">
          {{ mode === 'setup' ? reason : 'Abra su aplicación de autenticación y escriba el código de 6 dígitos.' }}
        </p>
      </div>
    </header>

    <ol v-if="mode === 'setup'" class="ui-2fa__steps">
      <li class="ui-2fa__step">
        <span class="ui-2fa__num" aria-hidden="true">1</span>
        <div class="ui-2fa__body">
          <p class="ui-2fa__step-title">Instale una aplicación de autenticación</p>
          <p class="ui-2fa__muted">Google Authenticator, Microsoft Authenticator o Authy, en su celular.</p>
        </div>
      </li>

      <li class="ui-2fa__step">
        <span class="ui-2fa__num" aria-hidden="true">2</span>
        <div class="ui-2fa__body">
          <p class="ui-2fa__step-title">Escanee este código con la aplicación</p>
          <div class="ui-2fa__scan">
            <div class="ui-2fa__qr">
              <img v-if="qr" :src="qr" alt="Código QR para la aplicación de autenticación" width="148" height="148" data-test="two-factor-qr" />
              <span v-else class="ui-2fa__muted" role="status">Preparando…</span>
            </div>
            <div class="ui-2fa__manual">
              <p class="ui-2fa__muted">En la aplicación, toque <strong>+</strong> y elija <strong>Escanear un código QR</strong>.</p>
              <p class="ui-2fa__muted">¿No puede escanear?</p>
              <button
                v-if="secret"
                type="button"
                class="ui-2fa__link"
                :aria-expanded="showKey"
                aria-controls="ui-2fa-key"
                data-test="two-factor-show-key"
                @click="showKey = !showKey"
              >
                <KeyRound :size="13" aria-hidden="true" />
                {{ showKey ? 'Ocultar la clave' : 'Usar una clave en su lugar' }}
              </button>
            </div>
          </div>
          <div v-if="secret && showKey" id="ui-2fa-key" class="ui-2fa__key">
            <code data-test="two-factor-secret">{{ groupedSecret }}</code>
            <button type="button" class="ui-2fa__copy" data-test="two-factor-copy" @click="copySecret">
              <component :is="copied ? Check : Copy" :size="14" aria-hidden="true" />
              {{ copied ? 'Copiada' : 'Copiar' }}
            </button>
          </div>
        </div>
      </li>

      <li class="ui-2fa__step">
        <span class="ui-2fa__num" aria-hidden="true">3</span>
        <div class="ui-2fa__body">
          <p class="ui-2fa__step-title">Escriba el código que muestra la aplicación</p>
          <OtpInput
            ref="otp"
            v-model="code"
            label="Código de 6 dígitos"
            :error="error"
            :disabled="busy || !qr"
            stretch
            autofocus
            @complete="emit('complete', $event)"
          />
        </div>
      </li>
    </ol>

    <template v-else>
      <OtpInput
        ref="otp"
        v-model="code"
        label="Código de 6 dígitos"
        :error="error"
        :disabled="busy"
        stretch
        autofocus
        @complete="emit('complete', $event)"
      />
      <p class="ui-2fa__timer" data-test="two-factor-timer">
        <svg viewBox="0 0 22 22" width="18" height="18" aria-hidden="true">
          <circle cx="11" cy="11" r="9" class="ui-2fa__ring-track" />
          <circle
            cx="11"
            cy="11"
            r="9"
            class="ui-2fa__ring"
            :stroke-dasharray="RING"
            :stroke-dashoffset="ringOffset"
          />
        </svg>
        <span>El código de su aplicación cambia en {{ remaining }} s.</span>
      </p>
    </template>

    <p class="ui-2fa__status" aria-live="polite">{{ status }}</p>

    <details v-if="mode === 'verify'" class="ui-2fa__help">
      <summary>¿No tiene su celular a mano?</summary>
      <p>{{ recoveryHint }}</p>
    </details>

    <button type="button" class="ui-2fa__back" :disabled="busy" @click="emit('back')">
      <ArrowLeft :size="14" aria-hidden="true" /> {{ backLabel }}
    </button>
  </div>
</template>

<style scoped>
.ui-2fa {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.ui-2fa__head {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.ui-2fa__badge {
  display: grid;
  place-items: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: var(--r-md);
  background: var(--brand-soft);
  color: var(--brand);
}

.ui-2fa__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
  line-height: 1.25;
}

.ui-2fa__lead {
  margin: var(--space-1) 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

/* Pasos como una línea de tiempo: el número marca el orden y la línea los une. */
.ui-2fa__steps {
  display: grid;
  gap: var(--space-5);
  margin: 0;
  padding: 0;
  list-style: none;
}

.ui-2fa__step {
  position: relative;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: var(--space-3);
}

.ui-2fa__step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 30px;
  bottom: calc(-1 * var(--space-5) + 4px);
  left: 12.5px;
  width: 1px;
  background: var(--border);
}

.ui-2fa__num {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  background: var(--surface-elev);
  font-size: 12px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.ui-2fa__body {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
  padding-top: 3px;
}

.ui-2fa__step-title {
  margin: 0;
  font-size: 13.5px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.ui-2fa__muted {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.ui-2fa__manual .ui-2fa__muted {
  display: block;
}

.ui-2fa__scan {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

/* Solo el QR va sobre blanco: los lectores necesitan contraste, la tarjeta no. */
.ui-2fa__qr {
  display: grid;
  place-items: center;
  flex: none;
  width: 160px;
  height: 160px;
  padding: 6px;
  border-radius: var(--r-md);
  background: #ffffff;
}

.ui-2fa__manual {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}

.ui-2fa__link {
  display: inline-flex;
  white-space: nowrap;
  align-items: center;
  gap: 6px;
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  text-decoration: underline;
  text-decoration-color: var(--border-strong);
  text-underline-offset: 3px;
  cursor: pointer;
}

.ui-2fa__key {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
}

.ui-2fa__key code {
  font-family: var(--font-mono);
  font-size: 13px;
  letter-spacing: 0.04em;
  word-break: break-word;
}

.ui-2fa__copy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  min-height: 30px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-elev);
  color: var(--text);
  font: inherit;
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.ui-2fa__timer {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: calc(-1 * var(--space-2)) 0 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.ui-2fa__ring-track,
.ui-2fa__ring {
  fill: none;
  stroke-width: 2.5;
}

.ui-2fa__ring-track {
  stroke: var(--border);
}

.ui-2fa__ring {
  stroke: var(--text-muted);
  stroke-linecap: round;
  transform: rotate(-90deg);
  transform-origin: center;
  transition: stroke-dashoffset 1s linear;
}

.ui-2fa__status {
  margin: calc(-1 * var(--space-3)) 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.ui-2fa__help {
  font-size: 12.5px;
  color: var(--text-muted);
}

.ui-2fa__help summary {
  cursor: pointer;
  color: var(--text);
  font-weight: var(--fw-medium);
}

.ui-2fa__help p {
  margin: var(--space-2) 0 0;
}

.ui-2fa__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 36px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.ui-2fa__back:hover:not(:disabled) {
  color: var(--text);
}

@media (max-width: 420px) {
  .ui-2fa__scan {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
