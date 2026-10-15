<script setup lang="ts">
import Button from './Button.vue'

/**
 * Barra fija al pie con "Cambios sin guardar", Descartar y Guardar. Aparece
 * cuando el formulario tiene cambios, así la acción queda a mano aunque el
 * formulario sea largo.
 */
withDefaults(
  defineProps<{
    visible: boolean
    saving?: boolean
    canSave?: boolean
    message?: string
    saveLabel?: string
  }>(),
  { canSave: true, message: 'Tenés cambios sin guardar', saveLabel: 'Guardar cambios' },
)

const emit = defineEmits<{ save: []; discard: [] }>()
</script>

<template>
  <Transition name="ui-unsaved">
    <div v-if="visible" class="ui-unsaved" role="region" aria-label="Cambios sin guardar">
      <span class="ui-unsaved__message">
        <span class="ui-unsaved__dot" aria-hidden="true" />
        {{ message }}
      </span>
      <div class="ui-unsaved__actions">
        <Button variant="ghost" :disabled="saving" @click="emit('discard')">Descartar</Button>
        <Button :loading="saving" :disabled="!canSave" @click="emit('save')">{{ saveLabel }}</Button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ui-unsaved {
  position: sticky;
  bottom: var(--space-4);
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-6);
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface-elev);
  box-shadow: var(--shadow-lg);
}

.ui-unsaved__message {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
}

.ui-unsaved__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--warning);
}

.ui-unsaved__actions {
  display: flex;
  gap: var(--space-2);
}

.ui-unsaved-enter-active,
.ui-unsaved-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-out);
}

.ui-unsaved-enter-from,
.ui-unsaved-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
