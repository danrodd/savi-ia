<script setup lang="ts">
import { Check, Copy } from 'lucide-vue-next'
import { onBeforeUnmount, ref, useId } from 'vue'

/** Valor de solo lectura (secreto, token, URL) con botón para copiarlo. */
const props = withDefaults(
  defineProps<{
    value: string
    label?: string
    hint?: string
    mono?: boolean
  }>(),
  { mono: true },
)

const emit = defineEmits<{ copied: [] }>()
const id = `copy-${useId()}`
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.value)
  } catch {
    // Sin permiso de portapapeles (HTTP plano, navegador viejo): se selecciona
    // el texto para que la persona lo copie a mano.
    const el = document.getElementById(id)
    if (el) window.getSelection()?.selectAllChildren(el)
    return
  }
  copied.value = true
  emit('copied')
  clearTimeout(timer)
  timer = setTimeout(() => (copied.value = false), 2000)
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="ui-copy">
    <span v-if="label" class="ui-copy__label">{{ label }}</span>
    <div class="ui-copy__box">
      <code :id="id" class="ui-copy__value" :class="{ 'ui-copy__value--mono': mono }">{{ value }}</code>
      <button
        type="button"
        class="ui-copy__button"
        :aria-label="copied ? 'Copiado' : `Copiar ${label ?? 'valor'}`"
        @click="copy"
      >
        <Check v-if="copied" :size="15" aria-hidden="true" />
        <Copy v-else :size="15" aria-hidden="true" />
        <span>{{ copied ? 'Copiado' : 'Copiar' }}</span>
      </button>
    </div>
    <p v-if="hint" class="ui-copy__hint">{{ hint }}</p>
    <span class="ui-copy__live" aria-live="polite">{{ copied ? 'Copiado al portapapeles' : '' }}</span>
  </div>
</template>

<style scoped>
.ui-copy {
  display: grid;
  gap: var(--space-1);
  min-width: 0;
}

.ui-copy__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.ui-copy__box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 40px;
  padding: var(--space-1) var(--space-1) var(--space-1) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-subtle);
}

.ui-copy__value {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text);
}

.ui-copy__value--mono {
  font-family: var(--font-mono);
  font-size: 12.5px;
  letter-spacing: 0.02em;
}

.ui-copy__button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
  min-height: 32px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-elev);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.ui-copy__button:hover {
  background: var(--surface-hover);
}

.ui-copy__button:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.ui-copy__hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--text-subtle);
}

.ui-copy__live {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
