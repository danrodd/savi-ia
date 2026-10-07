<script setup lang="ts">
import AuthImage from './AuthImage.vue'

/**
 * Miniatura removible de una imagen que va a viajar en un mensaje (composer
 * o edición). Muestra el estado de la subida y, si falló, permite reintentar.
 */
defineProps<{
  filename: string
  attachmentId: string | null
  previewUrl: string | null
  status: 'uploading' | 'done' | 'error'
  error?: string | null
}>()
const emit = defineEmits<{ remove: []; retry: [] }>()
</script>

<template>
  <li class="chip" :class="`chip--${status}`">
    <div class="chip__thumb">
      <AuthImage :attachment-id="attachmentId" :src="previewUrl" :alt="filename" />
      <span v-if="status === 'uploading'" class="chip__overlay" role="status" aria-label="Subiendo imagen">
        <span class="chip__spinner" />
      </span>
      <button
        v-else-if="status === 'error'"
        type="button"
        class="chip__overlay chip__overlay--error"
        :title="error ?? 'No se pudo subir'"
        :aria-label="`Reintentar subir ${filename}`"
        @click="emit('retry')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M3 12a9 9 0 1 0 3-6.7" />
          <path d="M3 4v5h5" />
        </svg>
        <span class="chip__error-text">{{ error ?? 'Reintentar' }}</span>
      </button>
    </div>
    <button
      type="button"
      class="chip__remove"
      :aria-label="`Quitar imagen ${filename}`"
      @click="emit('remove')"
    >
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12" />
      </svg>
    </button>
  </li>
</template>

<style scoped>
.chip {
  position: relative;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  list-style: none;
}

.chip__thumb {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
}

.chip--error .chip__thumb {
  border-color: var(--danger, #dc2626);
}

.chip__overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
}

.chip__overlay--error {
  align-content: center;
  gap: 2px;
  padding: 2px;
  border: none;
  cursor: pointer;
  background: rgba(127, 29, 29, 0.7);
  font-family: inherit;
}

.chip__overlay--error:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: -2px;
}

.chip__error-text {
  font-size: 8.5px;
  line-height: 1.1;
  text-align: center;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chip__spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: chip-spin 0.8s linear infinite;
}

@keyframes chip-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .chip__spinner {
    animation-duration: 2s;
  }
}

.chip__remove {
  position: absolute;
  top: -6px;
  right: -6px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  padding: 0;
  background: var(--surface-inverse);
  color: var(--surface);
  border: 1px solid var(--surface);
  border-radius: 50%;
  cursor: pointer;
}

.chip__remove:hover {
  opacity: 0.85;
}

.chip__remove:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 1px;
}
</style>
