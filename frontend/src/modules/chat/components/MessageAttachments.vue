<script setup lang="ts">
import { ref } from 'vue'
import Dialog from '@/components/ui/Dialog.vue'
import type { UIAttachment } from '../types'
import AuthImage from './AuthImage.vue'

/** Miniaturas de las imágenes de un mensaje; al hacer clic se abren a tamaño completo. */
defineProps<{ attachments: UIAttachment[] }>()

const opened = ref<UIAttachment | null>(null)
const lightboxOpen = ref(false)

function open(a: UIAttachment): void {
  opened.value = a
  lightboxOpen.value = true
}
</script>

<template>
  <ul v-if="attachments.length > 0" class="msg-attachments" :class="{ 'msg-attachments--single': attachments.length === 1 }">
    <li v-for="a in attachments" :key="a.id" class="msg-attachments__item">
      <button
        type="button"
        class="msg-attachments__btn"
        :aria-label="`Ver imagen ${a.filename}`"
        @click="open(a)"
      >
        <AuthImage :attachment-id="a.id" :src="a.previewUrl" :alt="a.filename" />
      </button>
    </li>
  </ul>

  <Dialog v-model:open="lightboxOpen" :title="opened?.filename ?? 'Imagen'" :max-width="960">
    <div v-if="opened" class="lightbox">
      <AuthImage :attachment-id="opened.id" :src="opened.previewUrl" :alt="opened.filename" class="lightbox__img" />
    </div>
  </Dialog>
</template>

<style scoped>
.msg-attachments {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
  width: 100%;
  margin: 0;
  padding: 0;
  list-style: none;
}

.msg-attachments--single {
  grid-template-columns: minmax(0, 220px);
}

.msg-attachments__item {
  min-width: 0;
}

.msg-attachments__btn {
  display: block;
  width: 100%;
  height: 120px;
  padding: 0;
  overflow: hidden;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  cursor: zoom-in;
}

.msg-attachments--single .msg-attachments__btn {
  height: auto;
  max-height: 200px;
  min-height: 80px;
}

.msg-attachments__btn:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

.lightbox {
  display: grid;
  place-items: center;
}

.lightbox :deep(.lightbox__img) {
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  border-radius: var(--r-md);
}
</style>
