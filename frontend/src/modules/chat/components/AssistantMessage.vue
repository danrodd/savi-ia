<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MessageVersion, UIMessage } from '../types'
import { groupToolCalls } from '../utils/groupToolCalls'
import BrandMark from './BrandMark.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ShareMenu from './ShareMenu.vue'
import ToolPill from './ToolPill.vue'
import VersionNavigator from './VersionNavigator.vue'

const props = withDefaults(
  defineProps<{
    message: UIMessage
    canRegenerate: boolean
    versions: MessageVersion[] | null
    /** ID de la conversación que contiene este mensaje. Lo recibe el menú
     *  de compartir para armar el deep link `/share/:id`. Null mientras la
     *  conversación está pendiente de persistirse en backend. */
    conversationId: string | null
    /** Vista compartida: oculta acciones que no aplican (regenerar, share
     *  por mensaje). Se mantiene Copiar porque es read-only seguro. */
    readOnly?: boolean
  }>(),
  { readOnly: false },
)
const emit = defineEmits<{ regenerate: [] }>()

const showCaret = computed(() => !props.message.done)
const showPlaceholder = computed(() => !props.message.done && props.message.text === '')
const copied = ref(false)
const versionIdx = ref<number | null>(null)
// Ref al nodo que contiene el markdown renderizado — lo necesita
// ShareMenu para exportar a HTML/PDF preservando tablas y listas.
const contentEl = ref<HTMLElement | null>(null)

const hasVersions = computed(() => (props.versions?.length ?? 0) > 1)
const totalVersions = computed(() => props.versions?.length ?? 0)
const displayedText = computed(() => {
  if (versionIdx.value === null) return props.message.text
  return props.versions?.[versionIdx.value]?.text ?? props.message.text
})
const displayedToolCalls = computed(() => {
  if (versionIdx.value === null) return props.message.toolCalls
  return props.versions?.[versionIdx.value]?.toolCalls ?? props.message.toolCalls
})
const displayedToolGroups = computed(() => groupToolCalls(displayedToolCalls.value))
const displayedInterrupted = computed(() => {
  if (versionIdx.value === null) return !!props.message.interrupted
  return props.versions?.[versionIdx.value]?.interrupted ?? false
})
const isViewingHistorical = computed(
  () =>
    versionIdx.value !== null &&
    props.versions !== null &&
    versionIdx.value < totalVersions.value - 1,
)

async function copyText(): Promise<void> {
  try {
    await navigator.clipboard.writeText(displayedText.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // ignore
  }
}

function prev(): void {
  if (versionIdx.value === null) versionIdx.value = totalVersions.value - 1
  if (versionIdx.value > 0) versionIdx.value--
}

function next(): void {
  if (versionIdx.value === null) return
  if (versionIdx.value < totalVersions.value - 1) versionIdx.value++
  else versionIdx.value = null
}
</script>

<template>
  <div class="assistant-message" :class="{ 'assistant-message--historical': isViewingHistorical }">
    <BrandMark :size="32" label="S" class="assistant-message__avatar" />

    <div class="assistant-message__body">
      <div class="assistant-message__meta">
        <span class="assistant-message__name">SAVI</span>
        <span v-if="message.done && !message.error" class="assistant-message__time">
          {{ isViewingHistorical ? 'Versión anterior' : 'Ahora' }}
        </span>
      </div>

      <div v-if="displayedToolGroups.length > 0" class="assistant-message__tools">
        <ToolPill v-for="group in displayedToolGroups" :key="group.label" :group="group" />
      </div>

      <div ref="contentEl" class="assistant-message__content">
        <span v-if="showPlaceholder" class="caret" aria-hidden="true" />
        <template v-else>
          <MarkdownRenderer :source="displayedText" />
          <span v-if="showCaret && !isViewingHistorical" class="caret" aria-hidden="true" />
        </template>
      </div>

      <p v-if="message.error && !isViewingHistorical" class="assistant-message__error">
        {{ message.error }}
      </p>
      <p v-if="displayedInterrupted" class="assistant-message__hint">Respuesta detenida.</p>

      <div v-if="message.done && !message.error" class="assistant-message__actions">
        <button
          type="button"
          class="action-btn"
          :title="copied ? 'Copiado' : 'Copiar'"
          @click="copyText"
        >
          <svg v-if="!copied" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span>{{ copied ? 'Copiado' : 'Copiar' }}</span>
        </button>
        <ShareMenu
          v-if="!readOnly"
          kind="message"
          placement="top-end"
          :text="displayedText"
          :conversation-id="conversationId"
          :content-ref="contentEl"
        />
        <button
          v-if="canRegenerate"
          type="button"
          class="action-btn"
          title="Regenerar respuesta"
          @click="emit('regenerate')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 0 1 14.85-6.85L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-14.85 6.85L3 16" />
            <path d="M3 21v-5h5" />
          </svg>
          <span>Regenerar</span>
        </button>
        <button
          v-if="hasVersions && versionIdx !== null"
          type="button"
          class="action-btn action-btn--exit"
          @click="versionIdx = null"
        >
          ← actual
        </button>
        <VersionNavigator
          v-if="hasVersions"
          :current="(versionIdx ?? totalVersions - 1) + 1"
          :total="totalVersions"
          @prev="prev"
          @next="next"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.assistant-message {
  display: flex;
  gap: var(--space-5);
  margin-bottom: var(--space-7);
  animation: fadeInUp 0.3s var(--ease-out);
  transition: opacity var(--duration-fast) var(--ease-out);
}

.assistant-message--historical .assistant-message__content {
  opacity: 0.78;
}

@media (max-width: 767px) {
  .assistant-message {
    gap: var(--space-3);
    margin-bottom: var(--space-6);
  }
  .assistant-message__content {
    font-size: 14px;
  }
}

.assistant-message__avatar {
  margin-top: 2px;
}

.assistant-message__body {
  flex: 1;
  min-width: 0;
}

.assistant-message__meta {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.assistant-message__name {
  font-family: var(--font-display);
  font-weight: var(--fw-semibold);
  font-size: 13px;
  letter-spacing: 0.01em;
  color: var(--text);
}

.assistant-message__time {
  font-size: 11.5px;
  color: var(--text-subtle);
  font-family: var(--font-mono);
}

.assistant-message__tools {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.assistant-message__content {
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--text);
  transition: opacity var(--duration-fast) var(--ease-out);
}

.caret {
  display: inline-block;
  width: 7px;
  height: 16px;
  background: var(--brand);
  vertical-align: text-bottom;
  margin-left: 2px;
  animation: blink 1s step-end infinite;
}

.assistant-message__error {
  margin: var(--space-3) 0 0;
  padding: var(--space-3) var(--space-4);
  background: var(--brand-soft);
  border: 1px solid var(--brand);
  border-radius: var(--r-md);
  color: var(--brand);
  font-size: 13px;
}

.assistant-message__hint {
  margin: var(--space-3) 0 0;
  font-size: 12.5px;
  color: var(--text-subtle);
  font-style: italic;
}

.assistant-message__actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-4);
  opacity: 0;
  transform: translateY(2px);
  transition: opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-out);
}

.assistant-message:hover .assistant-message__actions,
.assistant-message__actions:has(.nav),
.assistant-message__actions:has(.action-btn--exit) {
  opacity: 1;
  transform: translateY(0);
}

.action-btn {
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

.action-btn:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn--exit {
  color: var(--brand);
}

.action-btn--exit:hover {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

@media (max-width: 767px) {
  .assistant-message__actions {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
