<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { toast } from '@/lib/toast'
import { useAttachmentUploader } from '../composables/useAttachmentUploader'
import { useFileDrop } from '../composables/useFileDrop'
import type { UIAttachment } from '../types'
import { IMAGE_ACCEPT, isAllowedImageType } from '../utils/attachments'
import AttachmentChip from './AttachmentChip.vue'

const props = defineProps<{
  streaming: boolean
  disabled?: boolean
  /**
   * Texto que el backend rechazó por límite de uso o por turno en curso.
   * Vuelve al cuadro para que el usuario no pierda lo que escribió: el
   * rechazo es temporal y reescribirlo sería el peor castigo posible.
   */
  restoreText?: string | null
  /** Imágenes del mismo turno rechazado: vuelven a la tira, ya subidas. */
  restoreAttachments?: UIAttachment[] | null
}>()
const emit = defineEmits<{
  send: [text: string, attachments: UIAttachment[]]
  stop: []
  restored: []
}>()

const text = ref('')

const uploader = useAttachmentUploader({ onReject: (message) => toast.error(message) })

watch(
  () => [props.restoreText, props.restoreAttachments] as const,
  ([value, attachments]) => {
    const hasAttachments = (attachments?.length ?? 0) > 0
    if (!value && !hasAttachments) return
    // Sin pisar lo que el usuario ya haya empezado a escribir de nuevo.
    if (value && !text.value.trim()) text.value = value
    if (attachments && hasAttachments) uploader.restore(attachments)
    emit('restored')
    nextTick(autosize)
  },
)
const textarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const wrap = ref<HTMLElement | null>(null)

function autosize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

watch(text, () => {
  nextTick(autosize)
})

const canSend = computed(
  () =>
    (text.value.trim() !== '' || uploader.ready.value.length > 0) &&
    !uploader.uploading.value &&
    !uploader.hasError.value &&
    !props.streaming &&
    !props.disabled,
)

function submit(): void {
  if (!canSend.value) return
  emit('send', text.value.trim(), uploader.take())
  text.value = ''
  nextTick(autosize)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}

// ── Imágenes ─────────────────────────────────────────────────────────────
function onPaste(e: ClipboardEvent): void {
  if (props.disabled) return
  const files = Array.from(e.clipboardData?.files ?? []).filter((f) => isAllowedImageType(f.type))
  // Texto plano (o cualquier cosa sin imagen): el pegado normal no se toca.
  if (files.length === 0) return
  e.preventDefault()
  uploader.addFiles(files.map(namePastedCapture))
}

/** Una captura pegada llega como "image.png": se le pone la hora, que es
 * el nombre que se ve en la miniatura y en la vista ampliada. */
function namePastedCapture(file: File): File {
  if (file.name && file.name !== 'image.png') return file
  const time = new Date().toTimeString().slice(0, 8).replaceAll(':', '-')
  const extension = file.type.split('/')[1] ?? 'png'
  return new File([file], `captura-${time}.${extension}`, { type: file.type })
}

function openPicker(): void {
  fileInput.value?.click()
}

function onPick(e: Event): void {
  const input = e.target as HTMLInputElement
  if (input.files) uploader.addFiles(input.files)
  // Permite volver a elegir el mismo archivo.
  input.value = ''
}

// La zona de soltar es el contenedor del composer (todo el área del chat): el
// overlay se posiciona contra ese ancestro, que debe ser `position: relative`.
const { dragging } = useFileDrop(
  () => wrap.value?.parentElement,
  (files) => uploader.addFiles(files),
  () => !props.disabled,
)
</script>

<template>
  <div ref="wrap" class="composer-wrap">
    <div v-if="dragging" class="composer__drop" aria-hidden="true">
      <div class="composer__drop-card">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="9" cy="9" r="2" />
          <path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21" />
        </svg>
        Soltá las imágenes acá
      </div>
    </div>
    <form class="composer" :class="{ 'composer--focused': false }" @submit.prevent="submit">
      <ul v-if="uploader.items.value.length > 0" class="composer__attachments" aria-label="Imágenes adjuntas">
        <AttachmentChip
          v-for="item in uploader.items.value"
          :key="item.key"
          :filename="item.filename"
          :attachment-id="item.id"
          :preview-url="item.previewUrl || null"
          :status="item.status"
          :error="item.error"
          @remove="uploader.remove(item.key)"
          @retry="uploader.retry(item.key)"
        />
      </ul>
      <textarea
        ref="textarea"
        v-model="text"
        class="composer__input"
        rows="1"
        placeholder="Pregúntale a SAVI…"
        :disabled="disabled"
        @keydown="onKeydown"
        @paste="onPaste"
      />
      <input
        ref="fileInput"
        type="file"
        class="composer__file"
        :accept="IMAGE_ACCEPT"
        multiple
        tabindex="-1"
        aria-hidden="true"
        @change="onPick"
      />
      <div class="composer__row">
        <Tooltip text="Adjuntar imagen">
          <button
            type="button"
            class="composer__btn composer__btn--attach"
            aria-label="Adjuntar imagen"
            :disabled="disabled"
            @click="openPicker"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
        </Tooltip>
        <span class="composer__hint">
          <kbd>Enter</kbd> para enviar · <kbd>Shift</kbd>+<kbd>Enter</kbd> para nueva línea
        </span>
        <Tooltip v-if="streaming" text="Detener">
          <button
            type="button"
            class="composer__btn composer__btn--stop"
            aria-label="Detener"
            @click="emit('stop')"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        </Tooltip>
        <Tooltip v-else text="Enviar mensaje">
          <button
            type="submit"
            class="composer__btn composer__btn--send"
            aria-label="Enviar"
            :disabled="!canSend"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </Tooltip>
      </div>
    </form>
  </div>
</template>

<style scoped>
/* Sin `position: relative` a propósito: el overlay de soltar imágenes se ancla
   al contenedor del chat (área completa), no a esta franja. */
.composer-wrap {
  padding: var(--space-4) var(--space-7) var(--space-6);
  background: linear-gradient(to bottom, transparent, var(--surface) 30%);
  pointer-events: none;
  flex-shrink: 0;
}

@media (max-width: 767px) {
  .composer-wrap {
    padding: var(--space-3) var(--space-4) var(--space-4);
  }
}

.composer {
  position: relative;
  max-width: var(--composer-max-width);
  margin: 0 auto;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-md);
  transition: border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
  pointer-events: auto;
}

.composer:focus-within {
  border-color: var(--brand);
  box-shadow: 0 0 0 4px var(--brand-ring), var(--shadow-md);
}

.composer__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-4) var(--space-5) 0;
  list-style: none;
}

.composer__file {
  display: none;
}

.composer__input {
  display: block;
  width: 100%;
  min-height: 52px;
  max-height: 200px;
  padding: var(--space-5) var(--space-5) var(--space-1);
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-family: var(--font-sans);
  font-size: 14.5px;
  line-height: 1.5;
  color: var(--text);
}

.composer__input::placeholder {
  color: var(--text-subtle);
}

.composer__input:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.composer__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4) var(--space-3);
}

.composer__hint {
  margin-right: auto;
  font-size: 11px;
  color: var(--text-subtle);
  user-select: none;
}

@media (max-width: 767px) {
  .composer__hint {
    display: none;
  }
}

.composer__hint kbd {
  display: inline-block;
  padding: 1px 5px;
  margin: 0 1px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: 4px;
}

.composer__btn {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: var(--r-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  flex-shrink: 0;
}

.composer__btn:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}

.composer__btn--attach {
  background: transparent;
  color: var(--text-muted);
}

.composer__btn--attach:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text);
}

.composer__btn--attach:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.composer__btn--send {
  background: var(--brand);
  color: var(--text-on-brand);
  box-shadow: var(--shadow-inset), 0 1px 2px rgba(0, 0, 0, 0.1);
}

.composer__btn--send:hover:not(:disabled) {
  background: var(--brand-strong);
  transform: translateY(-0.5px);
}

.composer__btn--send:disabled {
  background: var(--surface-subtle);
  color: var(--text-subtle);
  cursor: not-allowed;
  box-shadow: none;
}

.composer__btn--stop {
  background: var(--surface-inverse);
  color: var(--surface);
}

.composer__btn--stop:hover {
  opacity: 0.85;
  transform: translateY(-0.5px);
}

.composer__drop {
  position: absolute;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, var(--surface) 82%, transparent);
  border: 2px dashed var(--brand);
  border-radius: var(--r-lg);
  pointer-events: none;
}

.composer__drop-card {
  display: grid;
  justify-items: center;
  gap: var(--space-3);
  padding: var(--space-6) 32px;
  background: var(--surface-elev);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-md);
  color: var(--brand);
  font-size: 15px;
  font-weight: var(--fw-semibold);
}
</style>
