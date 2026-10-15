<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

/**
 * Código de un solo uso en casillas (TOTP de 6 dígitos por defecto). Acepta el
 * código pegado entero, avanza solo y emite `complete` al llenarse, para que
 * el formulario se envíe sin un clic extra (el código vence en segundos).
 */
const props = withDefaults(
  defineProps<{
    length?: number
    label?: string
    error?: string | null
    disabled?: boolean
    autofocus?: boolean
  }>(),
  { length: 6, label: 'Código de verificación' },
)

const model = defineModel<string>({ default: '' })
const emit = defineEmits<{ complete: [code: string] }>()
const inputs = ref<HTMLInputElement[]>([])

const digits = computed(() =>
  // Un hueco (casilla salteada) se guarda como espacio y se muestra vacío.
  Array.from({ length: props.length }, (_, i) => model.value.charAt(i).trim()),
)

function focusAt(index: number): void {
  const target = inputs.value[Math.max(0, Math.min(index, props.length - 1))]
  target?.focus()
  target?.select()
}

function setFrom(index: number, raw: string): void {
  const clean = raw.replace(/\D/g, '')
  if (!clean) return
  const chars = model.value.padEnd(props.length, ' ').split('')
  for (let i = 0; i < clean.length && index + i < props.length; i++) {
    chars[index + i] = clean.charAt(i)
  }
  model.value = chars.join('').replace(/\s+$/, '').slice(0, props.length)
  focusAt(index + clean.length)
}

function onInput(index: number, event: Event): void {
  const el = event.target as HTMLInputElement
  const value = el.value
  el.value = digits.value[index] ?? ''
  setFrom(index, value)
}

function onKeydown(index: number, event: KeyboardEvent): void {
  if (event.key === 'Backspace') {
    event.preventDefault()
    const chars = model.value.split('')
    if (chars[index]) {
      chars.splice(index, 1)
      model.value = chars.join('')
      focusAt(index)
    } else if (index > 0) {
      chars.splice(index - 1, 1)
      model.value = chars.join('')
      focusAt(index - 1)
    }
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    focusAt(index - 1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    focusAt(index + 1)
  }
}

function onPaste(index: number, event: ClipboardEvent): void {
  event.preventDefault()
  setFrom(index, event.clipboardData?.getData('text') ?? '')
}

watch(model, (value) => {
  if (value.length === props.length && /^\d+$/.test(value)) emit('complete', value)
})

/** Limpia las casillas y vuelve a la primera (tras un código rechazado). */
function clear(): void {
  model.value = ''
  nextTick(() => focusAt(0))
}

defineExpose({ clear, focus: () => focusAt(model.value.length) })

onMounted(() => {
  if (props.autofocus) focusAt(0)
})
</script>

<template>
  <fieldset class="ui-otp" :disabled="disabled">
    <legend class="ui-otp__label">{{ label }}</legend>
    <div class="ui-otp__cells">
      <input
        v-for="(digit, index) in digits"
        :key="index"
        :ref="(el) => { if (el) inputs[index] = el as HTMLInputElement }"
        class="ui-otp__cell"
        :class="{ 'ui-otp__cell--invalid': !!error }"
        :value="digit"
        type="text"
        inputmode="numeric"
        :autocomplete="index === 0 ? 'one-time-code' : 'off'"
        maxlength="1"
        :aria-label="`Dígito ${index + 1} de ${length}`"
        :aria-invalid="error ? 'true' : undefined"
        @input="onInput(index, $event)"
        @keydown="onKeydown(index, $event)"
        @paste="onPaste(index, $event)"
        @focus="($event.target as HTMLInputElement).select()"
      />
    </div>
    <p v-if="error" class="ui-otp__error" role="alert">{{ error }}</p>
  </fieldset>
</template>

<style scoped>
.ui-otp {
  margin: 0;
  padding: 0;
  border: none;
  min-width: 0;
}

.ui-otp__label {
  margin-bottom: var(--space-3);
  padding: 0;
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.ui-otp__cells {
  display: flex;
  gap: var(--space-3);
}

.ui-otp__cell {
  width: 44px;
  height: 52px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: var(--fw-semibold);
  text-align: center;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.ui-otp__cell:focus-visible {
  outline: none;
  border-color: var(--brand);
  box-shadow: var(--focus-ring);
}

.ui-otp__cell--invalid {
  border-color: var(--danger);
}

.ui-otp:disabled .ui-otp__cell {
  opacity: 0.6;
}

.ui-otp__error {
  margin: var(--space-3) 0 0;
  font-size: 12px;
  font-weight: var(--fw-medium);
  color: var(--text-danger);
}

@media (max-width: 380px) {
  .ui-otp__cells {
    gap: var(--space-2);
  }

  .ui-otp__cell {
    width: 38px;
    height: 46px;
    font-size: 19px;
  }
}
</style>
