<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef } from 'vue'
import type { MessageVersion } from '../types'
import VersionNavigator from './VersionNavigator.vue'

const props = defineProps<{
  text: string
  messageId: string | null
  canEdit: boolean
  versions: MessageVersion[] | null
}>()
const emit = defineEmits<{ edit: [text: string] }>()

const editing = ref(false)
const draft = ref(props.text)
const textareaRef = useTemplateRef<HTMLTextAreaElement>('textarea')
const versionIdx = ref<number | null>(null)
const copied = ref(false)

async function copyText(): Promise<void> {
  try {
    await navigator.clipboard.writeText(displayText.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // ignore
  }
}

const hasVersions = computed(() => (props.versions?.length ?? 0) > 1)
const totalVersions = computed(() => props.versions?.length ?? 0)
const displayText = computed(() => {
  if (versionIdx.value === null) return props.text
  return props.versions?.[versionIdx.value]?.text ?? props.text
})
const isViewingHistorical = computed(
  () =>
    versionIdx.value !== null &&
    props.versions !== null &&
    versionIdx.value < totalVersions.value - 1,
)

function autosize(): void {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 240)}px`
}

async function startEdit(): Promise<void> {
  draft.value = props.text
  editing.value = true
  await nextTick()
  autosize()
  textareaRef.value?.focus()
  textareaRef.value?.setSelectionRange(draft.value.length, draft.value.length)
}

function cancel(): void {
  editing.value = false
  draft.value = props.text
}

function submit(): void {
  const next = draft.value.trim()
  if (!next || next === props.text) {
    cancel()
    return
  }
  editing.value = false
  emit('edit', next)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    cancel()
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
  <div class="user-message" :class="{ 'user-message--editing': editing }">
    <div class="user-message__col">
      <div v-if="editing" class="bubble bubble--editing">
        <textarea
          ref="textarea"
          v-model="draft"
          class="bubble__input"
          rows="1"
          maxlength="16000"
          @input="autosize"
          @keydown="onKeydown"
        />
        <div class="bubble__actions">
          <button type="button" class="bubble__btn bubble__btn--ghost" @click="cancel">
            Cancelar
          </button>
          <button
            type="button"
            class="bubble__btn bubble__btn--primary"
            :disabled="!draft.trim() || draft.trim() === text"
            @click="submit"
          >
            Enviar
          </button>
        </div>
      </div>
      <div v-else class="bubble" :class="{ 'bubble--historical': isViewingHistorical }">
        {{ displayText }}
      </div>

      <div v-if="!editing" class="user-message__meta">
        <button
          type="button"
          class="meta-btn"
          :title="copied ? 'Copiado' : 'Copiar'"
          @click="copyText"
        >
          <svg v-if="!copied" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          <svg v-else width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          {{ copied ? 'Copiado' : 'Copiar' }}
        </button>
        <button v-if="canEdit" type="button" class="meta-btn" @click="startEdit">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
          Editar
        </button>
        <button
          v-if="hasVersions && versionIdx !== null"
          type="button"
          class="meta-btn meta-btn--exit"
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
.user-message {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-7);
  animation: fadeInUp 0.3s var(--ease-out);
}

.user-message__col {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
  max-width: 75%;
  min-width: 0;
  transition: max-width var(--duration-normal) var(--ease-out);
}

.user-message--editing .user-message__col {
  width: 100%;
  max-width: min(640px, 95%);
  align-items: stretch;
}

.bubble {
  padding: var(--space-3) var(--space-5);
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: 16px 16px 4px 16px;
  color: var(--text);
  font-size: 14.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.bubble--historical {
  opacity: 0.78;
  background: var(--surface);
  border-style: dashed;
}

.bubble--editing {
  width: 100%;
  background: var(--surface-elev);
  border-color: var(--brand);
  border-radius: var(--r-lg);
  box-shadow: 0 0 0 3px var(--brand-ring);
  padding: var(--space-4) var(--space-5);
}

.bubble__input {
  display: block;
  width: 100%;
  min-height: 24px;
  max-height: 240px;
  padding: 0;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font: inherit;
  line-height: 1.55;
  color: var(--text);
}

.bubble__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.bubble__btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid var(--border);
  background: transparent;
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.bubble__btn--ghost {
  color: var(--text-muted);
}

.bubble__btn--ghost:hover {
  background: var(--surface-subtle);
  color: var(--text);
}

.bubble__btn--primary {
  background: var(--brand);
  color: var(--text-on-brand);
  border-color: var(--brand);
}

.bubble__btn--primary:hover:not(:disabled) {
  background: var(--brand-strong);
  border-color: var(--brand-strong);
}

.bubble__btn--primary:disabled {
  background: var(--surface-subtle);
  border-color: var(--border);
  color: var(--text-subtle);
  cursor: not-allowed;
}

.user-message__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  opacity: 0;
  transform: translateY(-2px);
  transition: opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-out);
}

.user-message:hover .user-message__meta,
.user-message__meta:has(.nav),
.user-message__meta:has(.meta-btn--exit) {
  opacity: 1;
  transform: translateY(0);
}

.meta-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px var(--space-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  font-family: inherit;
  font-size: 11px;
  font-weight: var(--fw-medium);
  color: var(--text-subtle);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.meta-btn:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.meta-btn--exit {
  color: var(--brand);
}

.meta-btn--exit:hover {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

@media (max-width: 767px) {
  .user-message {
    margin-bottom: var(--space-6);
  }
  .user-message__col {
    max-width: 88%;
  }
  .user-message--editing .user-message__col {
    max-width: 100%;
  }
  .bubble {
    font-size: 14px;
  }
  .user-message__meta {
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
</style>
