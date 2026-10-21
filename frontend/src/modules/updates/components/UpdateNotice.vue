<script setup lang="ts">
/**
 * Avisos de la actualización automática (spec 09, sección 6).
 *
 * - Barra superior: versión nueva recomendada, u obligatoria con fecha límite.
 * - Diálogo que no se cierra: obligatoria con el plazo vencido.
 * - Diálogo de progreso: descarga, espera de turnos e instalación.
 *
 * En una instalación en servidor, desde otro equipo no se puede aceptar el
 * permiso de administrador: en lugar del botón se pide avisar a sistemas.
 */
import { computed, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { useUpdateStatus } from '../composables/useUpdateStatus'
import { bannerMessage, progressMessage, progressPercent } from '../utils/updateView'

const REMOTE_MESSAGE = 'Avise a su área de sistemas para que actualice SAVI desde el servidor.'

const { status, kind, applyError, apply, snooze } = useUpdateStatus()
const showNotes = ref(false)

const error = computed(() => applyError.value ?? status.value?.error ?? null)
const notes = computed(() => status.value?.notes?.trim() || null)
const percent = computed(() => (status.value === null ? null : progressPercent(status.value)))
</script>

<template>
  <div v-if="kind === 'banner' && status" class="update-banner" role="status">
    <div class="update-banner__row">
      <p class="update-banner__text">
        {{ bannerMessage(status) }}
        <button
          v-if="notes"
          type="button"
          class="update-banner__link"
          :aria-expanded="showNotes"
          @click="showNotes = !showNotes"
        >
          Qué cambió
        </button>
      </p>
      <div class="update-banner__actions">
        <template v-if="status.can_apply">
          <Button size="sm" @click="apply">
            {{ error ? 'Reintentar' : 'Actualizar y reiniciar' }}
          </Button>
          <Button size="sm" variant="ghost" @click="snooze">Más tarde</Button>
        </template>
        <template v-else>
          <span class="update-banner__remote">{{ REMOTE_MESSAGE }}</span>
          <Button size="sm" variant="ghost" @click="snooze">Más tarde</Button>
        </template>
      </div>
    </div>
    <p v-if="error" class="update-banner__error" role="alert">{{ error }}</p>
    <p v-if="showNotes && notes" class="update-banner__notes">{{ notes }}</p>
  </div>

  <Dialog
    v-if="kind === 'blocked' && status"
    :open="true"
    :dismissible="false"
    title="Debe actualizar SAVI"
    description="Esta versión de SAVI ya no es compatible. Debe actualizar para seguir usándola."
  >
    <p v-if="!status.can_apply" class="update-dialog__text">{{ REMOTE_MESSAGE }}</p>
    <p v-if="error" class="update-banner__error" role="alert">{{ error }}</p>
    <template v-if="status.can_apply" #footer>
      <Button @click="apply">{{ error ? 'Reintentar' : 'Actualizar ahora' }}</Button>
    </template>
  </Dialog>

  <Dialog
    v-if="kind === 'progress'"
    :open="true"
    :dismissible="false"
    title="Actualizando SAVI"
  >
    <p class="update-dialog__text" aria-live="polite">
      {{ status ? progressMessage(status) : 'Reiniciando SAVI…' }}
    </p>
    <div
      v-if="status?.phase === 'downloading' && percent !== null"
      class="update-progress"
      role="progressbar"
      :aria-valuenow="percent"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="update-progress__bar" :style="{ width: `${percent}%` }" />
    </div>
    <p class="update-dialog__hint">La página se recarga sola cuando SAVI vuelva a abrir.</p>
  </Dialog>
</template>

<style scoped>
.update-banner {
  position: fixed;
  top: var(--space-3);
  left: 50%;
  z-index: 800;
  transform: translateX(-50%);
  width: min(720px, calc(100vw - 2 * var(--space-4)));
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface-elev);
  box-shadow: var(--shadow-md);
  color: var(--text);
}

.update-banner__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.update-banner__text {
  margin: 0;
  font-size: 14px;
}

.update-banner__link {
  margin-left: var(--space-2);
  padding: 0;
  border: 0;
  background: none;
  color: var(--brand);
  font: inherit;
  text-decoration: underline;
  cursor: pointer;
}

.update-banner__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.update-banner__remote {
  font-size: 13px;
  color: var(--text-muted);
}

.update-banner__error {
  margin: var(--space-2) 0 0;
  font-size: 13px;
  color: var(--text-danger);
}

.update-banner__notes {
  margin: var(--space-2) 0 0;
  white-space: pre-line;
  font-size: 13px;
  color: var(--text-muted);
}

.update-dialog__text {
  margin: 0;
}

.update-dialog__hint {
  margin: var(--space-3) 0 0;
  font-size: 13px;
  color: var(--text-subtle);
}

.update-progress {
  height: 6px;
  margin-top: var(--space-3);
  overflow: hidden;
  border-radius: var(--r-pill);
  background: var(--surface-subtle);
}

.update-progress__bar {
  height: 100%;
  background: var(--brand);
  transition: width 0.3s ease;
}
</style>
