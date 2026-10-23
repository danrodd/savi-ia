<script setup lang="ts">
/**
 * Avisos de la actualización automática (spec 09, sección 6).
 *
 * - Barra superior: versión nueva recomendada, u obligatoria con fecha límite.
 * - Aviso del resultado del último intento: se muestra una sola vez.
 * - Diálogo que no se cierra: obligatoria con el plazo vencido.
 * - Diálogo de progreso: descarga, espera de turnos e instalación.
 *
 * En una instalación en servidor, desde otro equipo no se puede aceptar el
 * permiso de administrador: en lugar del botón se pide avisar a sistemas.
 */
import { computed, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { renderMarkdown } from '@/lib/markdown'
import { useUpdateStatus } from '../composables/useUpdateStatus'
import {
  bannerMessage,
  progressMessage,
  progressPercent,
  STALLED_MESSAGE,
} from '../utils/updateView'

const REMOTE_MESSAGE = 'Avise a su área de sistemas para que actualice SAVI desde el servidor.'

const { status, kind, applyError, stalled, result, apply, snooze, dismissResult, giveUpWaiting } =
  useUpdateStatus()
const showNotes = ref(false)

const error = computed(() => applyError.value ?? status.value?.error ?? null)
const notes = computed(() => status.value?.notes?.trim() || null)
const percent = computed(() => (status.value === null ? null : progressPercent(status.value)))
const showBanner = computed(() => kind.value === 'banner' && status.value !== null)
</script>

<template>
  <div v-if="showBanner || result" class="update-stack">
    <div
      v-if="result"
      class="update-banner"
      :class="`update-banner--${result.tone}`"
      role="status"
      data-testid="update-result"
    >
      <div class="update-banner__row">
        <p class="update-banner__text">{{ result.message }}</p>
        <div class="update-banner__actions">
          <Button size="sm" variant="ghost" @click="dismissResult">Entendido</Button>
        </div>
      </div>
    </div>

    <div v-if="showBanner && status" class="update-banner" role="status">
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
      <div
        v-if="showNotes && notes"
        class="update-banner__notes"
        v-html="renderMarkdown(notes)"
      />
    </div>
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
    <p v-if="stalled" class="update-banner__error" role="alert">{{ STALLED_MESSAGE }}</p>
    <p v-else class="update-dialog__hint">La página se recarga sola cuando SAVI vuelva a abrir.</p>
    <template v-if="stalled" #footer>
      <Button variant="ghost" @click="giveUpWaiting">Dejar de esperar</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.update-stack {
  position: fixed;
  top: var(--space-3);
  left: 50%;
  z-index: 800;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  transform: translateX(-50%);
  width: min(720px, calc(100vw - 2 * var(--space-4)));
}

.update-banner {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface-elev);
  box-shadow: var(--shadow-md);
  color: var(--text);
}

.update-banner--success {
  border-left: 4px solid var(--success);
}

.update-banner--warning {
  border-left: 4px solid var(--warning);
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
  font-size: 13px;
  color: var(--text-muted);
}

.update-banner__notes :deep(h1),
.update-banner__notes :deep(h2),
.update-banner__notes :deep(h3) {
  margin: 0 0 var(--space-1);
  font-size: 13px;
  font-weight: var(--fw-semibold);
}

.update-banner__notes :deep(ul) {
  margin: 0;
  padding-left: var(--space-5);
}

.update-banner__notes :deep(p) {
  margin: 0 0 var(--space-1);
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
