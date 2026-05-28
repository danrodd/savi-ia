<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ streaming: boolean; disabled?: boolean }>()
const emit = defineEmits<{ send: [text: string]; stop: [] }>()

const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

function autosize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

watch(text, () => {
  nextTick(autosize)
})

function submit(): void {
  const trimmed = text.value.trim()
  if (!trimmed || props.streaming || props.disabled) return
  emit('send', trimmed)
  text.value = ''
  nextTick(autosize)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="composer-wrap">
    <form class="composer" :class="{ 'composer--focused': false }" @submit.prevent="submit">
      <textarea
        ref="textarea"
        v-model="text"
        class="composer__input"
        rows="1"
        placeholder="Pregúntale a SAVI…"
        :disabled="disabled"
        @keydown="onKeydown"
      />
      <div class="composer__row">
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
            :disabled="!text.trim() || disabled"
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
.composer-wrap {
  position: relative;
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
</style>
