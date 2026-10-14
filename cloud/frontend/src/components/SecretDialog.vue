<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  /** El valor que se muestra una sola vez (token o contraseña temporal). */
  secret: string
  instructions: string
}>()

const emit = defineEmits<{ close: [] }>()

const copied = ref(false)
watch(
  () => props.open,
  () => {
    copied.value = false
  },
)

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.secret)
    copied.value = true
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <div v-if="open" class="overlay">
    <div class="dialog card" role="dialog" aria-modal="true" :aria-label="title">
      <h2>{{ title }}</h2>
      <p class="warning">
        Se muestra <strong>una sola vez</strong>. Al cerrar esta ventana no se puede volver a ver.
      </p>
      <code class="secret" data-test="secret">{{ secret }}</code>
      <p class="muted">{{ instructions }}</p>
      <div class="row actions">
        <button class="btn" type="button" @click="copy">
          {{ copied ? 'Copiado' : 'Copiar' }}
        </button>
        <button class="btn btn-primary" type="button" @click="emit('close')">Ya lo guardé</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgb(0 0 0 / 0.5);
}
.dialog {
  display: grid;
  gap: 0.9rem;
  width: min(520px, 100%);
}
.warning {
  margin: 0;
  padding: 0.5rem 0.7rem;
  border-radius: 8px;
  background: var(--warn-bg);
  color: var(--warn);
}
.secret {
  display: block;
  padding: 0.7rem;
  border: 1px dashed var(--border);
  border-radius: 8px;
  background: var(--surface-2);
  word-break: break-all;
  user-select: all;
}
.actions {
  justify-content: flex-end;
}
</style>
