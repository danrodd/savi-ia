<script setup lang="ts">
import { computed } from 'vue'
import { useAttachmentUrl } from '../composables/useAttachmentUrl'

/**
 * Imagen adjunta del chat. Con `src` (miniatura local) la muestra directo; si
 * no, pide los bytes autenticados por `attachmentId` (con caché de sesión).
 */
const props = defineProps<{
  attachmentId: string | null
  src?: string | null
  alt: string
}>()

const { url, status } = useAttachmentUrl(() => (props.src ? null : props.attachmentId))
const resolved = computed(() => props.src || url.value)
</script>

<template>
  <img v-if="resolved" :src="resolved" :alt="alt" class="auth-image" draggable="false" />
  <span v-else-if="status === 'error'" class="auth-image auth-image--state" role="img" :aria-label="`${alt} (no disponible)`">
    No disponible
  </span>
  <span v-else class="auth-image auth-image--state auth-image--loading" role="img" :aria-label="`Cargando ${alt}`" />
</template>

<style scoped>
.auth-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.auth-image--state {
  display: grid;
  place-items: center;
  background: var(--surface-subtle);
  color: var(--text-subtle);
  font-size: 11px;
}

.auth-image--loading {
  animation: auth-image-pulse 1.2s ease-in-out infinite;
}

@keyframes auth-image-pulse {
  50% {
    opacity: 0.5;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-image--loading {
    animation: none;
  }
}
</style>
