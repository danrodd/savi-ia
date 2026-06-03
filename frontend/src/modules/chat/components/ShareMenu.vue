<script setup lang="ts">
/**
 * Menú de compartir/descargar, usado en dos modos:
 *  - `kind="message"`: comparte UN mensaje del asistente.
 *  - `kind="conversation"`: comparte la conversación completa.
 *
 * Acciones disponibles:
 *  1. Compartir (Web Share API nativo del sistema, si está disponible).
 *  2. Copiar enlace a la conversación (solo si ya está guardada en BD).
 *  3. Descargar como HTML (DOM renderizado envuelto en doc standalone).
 *  4. Imprimir / Guardar como PDF (abre ventana y dispara print).
 *  5. Descargar como Markdown (texto fuente, fiel al original).
 *
 * Por qué un solo componente para los dos modos:
 *   Las cinco acciones son las mismas, solo cambia el "qué" se comparte:
 *   un nodo del DOM y un string de texto. El padre los provee.
 *   Alternativa descartada: dos componentes separados — duplicación
 *   innecesaria y inconsistencia de UX entre los dos contextos.
 *
 * Por qué pasar `contentRef` desde el padre en vez de queryselectorear:
 *   En Vue tener un templateRef explícito es más robusto que adivinar
 *   selectores. Si el DOM cambia, el ref sigue válido sin tocar este
 *   componente.
 */
import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

import { toast } from '@/lib/toast'
import {
  buildConversationUrl,
  downloadMarkdown,
  exportHtml,
  printPdf,
  tryWebShare,
} from '../lib/exportContent'

const props = withDefaults(
  defineProps<{
    /** Texto plano/markdown que se comparte/descarga como .md y como teaser de Web Share. */
    text: string
    /** ID de la conversación. Si es null, "copiar enlace" queda deshabilitado. */
    conversationId: string | null
    /** Ref al nodo del DOM con el contenido renderizado. Usado para HTML y PDF. */
    contentRef: Ref<HTMLElement | null>
    /** Modo del menú: cambia textos y comportamiento del Web Share. */
    kind?: 'message' | 'conversation'
    /** Título corto para el archivo y el Web Share. Default según `kind`. */
    title?: string
    /** Posición del popover relativa al botón. */
    placement?: 'bottom-end' | 'bottom-start' | 'top-end'
  }>(),
  { kind: 'message', placement: 'bottom-end' },
)

const open = ref(false)
const rootRef = ref<HTMLDivElement | null>(null)

const isWebShareSupported = typeof navigator !== 'undefined' && 'share' in navigator

function close(): void {
  open.value = false
}

function onWindowClick(e: MouseEvent): void {
  if (!rootRef.value?.contains(e.target as Node)) close()
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('mousedown', onWindowClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onWindowClick)
  document.removeEventListener('keydown', onKey)
})

function effectiveTitle(): string {
  if (props.title) return props.title
  return props.kind === 'conversation' ? 'Conversación con SAVI' : 'Respuesta de SAVI'
}

function getLinkOrNull(): string | null {
  return props.conversationId ? buildConversationUrl(props.conversationId) : null
}

async function handleShare(): Promise<void> {
  close()
  const link = getLinkOrNull()
  const ok = await tryWebShare({
    title: effectiveTitle(),
    text: props.text.slice(0, 280),
    ...(link ? { url: link } : {}),
  })
  if (!ok) {
    // Fallback: copiamos el enlace al portapapeles si hay; si no, el texto.
    try {
      await navigator.clipboard.writeText(link ?? props.text)
      toast.success(link ? 'Enlace copiado' : 'Texto copiado')
    } catch {
      toast.error('No se pudo compartir')
    }
  }
}

async function handleCopyLink(): Promise<void> {
  close()
  const link = getLinkOrNull()
  if (!link) return
  try {
    await navigator.clipboard.writeText(link)
    toast.success('Enlace copiado')
  } catch {
    toast.error('No se pudo copiar el enlace')
  }
}

function handleDownloadHtml(): void {
  close()
  const node = props.contentRef.value
  if (!node) {
    toast.error('No pude leer el contenido')
    return
  }
  exportHtml(node, effectiveTitle())
  toast.success('HTML descargado')
}

function handlePrintPdf(): void {
  close()
  const node = props.contentRef.value
  if (!node) {
    toast.error('No pude leer el contenido')
    return
  }
  printPdf(node, effectiveTitle())
}

function handleDownloadMd(): void {
  close()
  downloadMarkdown(props.text, effectiveTitle())
  toast.success('Descarga iniciada')
}
</script>

<template>
  <div
    ref="rootRef"
    class="share-menu"
    :class="[`share-menu--${placement}`, { 'share-menu--open': open }]"
  >
    <button
      type="button"
      class="share-menu__trigger"
      :aria-haspopup="'menu'"
      :aria-expanded="open"
      :title="kind === 'conversation' ? 'Compartir conversación' : 'Compartir'"
      @click="open = !open"
    >
      <slot name="trigger">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
          <polyline points="16 6 12 2 8 6" />
          <line x1="12" y1="2" x2="12" y2="15" />
        </svg>
        <span v-if="kind === 'message'">Compartir</span>
        <span v-else>Compartir conversación</span>
      </slot>
    </button>

    <div v-if="open" role="menu" class="share-menu__panel">
      <button
        v-if="isWebShareSupported"
        type="button"
        role="menuitem"
        class="share-menu__item"
        @click="handleShare"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="18" cy="5" r="3" />
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
        <span>Compartir…</span>
        <span class="share-menu__hint">Sistema</span>
      </button>

      <button
        type="button"
        role="menuitem"
        class="share-menu__item"
        :disabled="!conversationId"
        :title="conversationId ? '' : 'La conversación aún no se guardó'"
        @click="handleCopyLink"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
        <span>Copiar enlace</span>
      </button>

      <button
        type="button"
        role="menuitem"
        class="share-menu__item"
        @click="handleDownloadHtml"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span>Descargar como HTML</span>
      </button>

      <button
        type="button"
        role="menuitem"
        class="share-menu__item"
        @click="handlePrintPdf"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="6 9 6 2 18 2 18 9" />
          <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
          <rect x="6" y="14" width="12" height="8" />
        </svg>
        <span>Imprimir / Guardar como PDF</span>
      </button>

      <button
        type="button"
        role="menuitem"
        class="share-menu__item"
        @click="handleDownloadMd"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <span>Descargar como .md</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.share-menu {
  position: relative;
  display: inline-flex;
}

/* Cuando está abierto, elevamos la stacking context del root para que el
   panel quede por encima de mensajes/avatares posteriores en el DOM.
   El z-index del panel solo afecta DENTRO del contexto local — necesitamos
   elevar el root mismo para ganar contra hermanos siguientes. */
.share-menu--open {
  z-index: 40;
}

.share-menu__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-subtle);
  font-family: inherit;
  font-size: 11.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.share-menu__trigger:hover {
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.share-menu__panel {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 30;
  min-width: 220px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  animation: share-menu-in var(--duration-fast) var(--ease-out);
}

.share-menu--bottom-start .share-menu__panel {
  left: 0;
  right: auto;
}

.share-menu--top-end .share-menu__panel {
  top: auto;
  bottom: calc(100% + 4px);
}

@keyframes share-menu-in {
  from {
    opacity: 0;
    transform: translateY(-2px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.share-menu__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text);
  font-family: inherit;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-out);
}

.share-menu__item:hover:not(:disabled) {
  background: var(--surface-hover);
}

.share-menu__item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.share-menu__item span:nth-of-type(1) {
  flex: 1;
}

.share-menu__hint {
  font-size: 10.5px;
  color: var(--text-subtle);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
</style>
