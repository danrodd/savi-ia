<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel: string
  danger?: boolean
  /** Si se define, hay que escribir exactamente este texto para habilitar el botón. */
  typeToConfirm?: string
  busy?: boolean
}>()

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const typed = ref('')
watch(
  () => props.open,
  () => {
    typed.value = ''
  },
)

const canConfirm = computed(
  () => !props.busy && (!props.typeToConfirm || typed.value === props.typeToConfirm),
)
</script>

<template>
  <div v-if="open" class="overlay" @keydown.esc="emit('cancel')">
    <div class="dialog card" role="dialog" aria-modal="true" :aria-label="title">
      <h2>{{ title }}</h2>
      <p>{{ message }}</p>
      <label v-if="typeToConfirm">
        Para continuar escribí <strong>{{ typeToConfirm }}</strong>
        <input v-model="typed" autocomplete="off" />
      </label>
      <div class="row actions">
        <button class="btn" type="button" @click="emit('cancel')">Cancelar</button>
        <button
          class="btn"
          :class="danger ? 'btn-danger' : 'btn-primary'"
          type="button"
          :disabled="!canConfirm"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: rgb(0 0 0 / 0.45);
}
.dialog {
  display: grid;
  gap: 0.9rem;
  width: min(440px, 100%);
}
.actions {
  justify-content: flex-end;
}
</style>
