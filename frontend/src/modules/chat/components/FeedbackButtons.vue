<script setup lang="ts">
/**
 * "Me sirvió" / "No me sirvió" de una respuesta.
 *
 * 👍 guarda en el acto; 👎 pide el motivo en un diálogo corto. Tocar la
 * calificación activa la quita. El estado vive en `message.feedback` (lo
 * trae el backend); la UI es optimista y el store revierte si falla.
 */

import { Button, Dialog } from '@savi/ui'
import { computed, ref } from 'vue'
import { toast } from '@/lib/toast'
import { useChatStore } from '../stores/chatStore'
import type { FeedbackInput, FeedbackReason, MessageFeedback } from '../types'
import { FEEDBACK_COMMENT_MAX, FEEDBACK_REASONS, resolveFeedbackClick } from '../utils/feedback'

const props = defineProps<{
  /** ID real del mensaje (el backend lo asigna al persistir). */
  messageId: string
  feedback: MessageFeedback | null | undefined
}>()

const store = useChatStore()

const dialogOpen = ref(false)
const reason = ref<FeedbackReason | null>(null)
const comment = ref('')
const sending = ref(false)

const isUp = computed(() => props.feedback?.rating === 'up')
const isDown = computed(() => props.feedback?.rating === 'down')

async function save(input: FeedbackInput): Promise<boolean> {
  const ok = await store.rateMessage(props.messageId, input)
  if (ok) toast.success('¡Gracias!')
  else toast.error('No pudimos guardar su calificación. Pruebe de nuevo.')
  return ok
}

async function onClick(clicked: 'up' | 'down'): Promise<void> {
  const outcome = resolveFeedbackClick(props.feedback, clicked)
  if (outcome.kind === 'clear') {
    const ok = await store.rateMessage(props.messageId, null)
    if (!ok) toast.error('No pudimos quitar su calificación. Pruebe de nuevo.')
    return
  }
  if (outcome.kind === 'save') {
    await save(outcome.input)
    return
  }
  reason.value = null
  comment.value = ''
  dialogOpen.value = true
}

async function submitDown(): Promise<void> {
  if (sending.value) return
  sending.value = true
  try {
    const ok = await save({ rating: 'down', reason: reason.value, comment: comment.value })
    if (ok) dialogOpen.value = false
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <span class="feedback" role="group" aria-label="¿Le sirvió esta respuesta?">
    <button
      type="button"
      class="action-btn feedback__btn"
      :class="{ 'feedback__btn--active': isUp }"
      :aria-pressed="isUp"
      aria-label="Me sirvió"
      title="Me sirvió"
      data-testid="feedback-up"
      @click="onClick('up')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" :fill="isUp ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M7 10v12" />
        <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
      </svg>
    </button>
    <button
      type="button"
      class="action-btn feedback__btn"
      :class="{ 'feedback__btn--active feedback__btn--down': isDown }"
      :aria-pressed="isDown"
      aria-label="No me sirvió"
      title="No me sirvió"
      data-testid="feedback-down"
      @click="onClick('down')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" :fill="isDown ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M17 14V2" />
        <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
      </svg>
    </button>

    <Dialog v-model:open="dialogOpen" title="¿Qué pasó?" :max-width="420">
      <form class="fb-form" data-testid="feedback-dialog" @submit.prevent="submitDown">
        <fieldset class="fb-form__reasons">
          <legend class="fb-form__legend">Elija lo que mejor describa el problema</legend>
          <label v-for="option in FEEDBACK_REASONS" :key="option.value" class="fb-form__option">
            <input v-model="reason" type="radio" name="feedback-reason" :value="option.value" />
            <span>{{ option.label }}</span>
          </label>
        </fieldset>
        <label class="fb-form__comment">
          <span class="fb-form__legend">Contanos más (opcional)</span>
          <textarea
            v-model="comment"
            rows="3"
            :maxlength="FEEDBACK_COMMENT_MAX"
            placeholder="Contanos más (opcional)"
          />
        </label>
        <div class="fb-form__actions">
          <Button variant="ghost" size="sm" type="button" @click="dialogOpen = false">
            Cancelar
          </Button>
          <Button variant="primary" size="sm" type="submit" :loading="sending">Enviar</Button>
        </div>
      </form>
    </Dialog>
  </span>
</template>

<style scoped>
.feedback {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.feedback__btn--active {
  color: var(--brand-strong);
  background: var(--brand-soft);
}

.feedback__btn--active:hover:not(:disabled) {
  color: var(--brand-strong);
  background: var(--brand-soft);
}

.fb-form {
  display: grid;
  gap: var(--space-4);
}

.fb-form__reasons {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: none;
}

.fb-form__legend {
  margin-bottom: var(--space-2);
  font-size: 12.5px;
  color: var(--text-muted);
}

.fb-form__option {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-size: 13.5px;
  cursor: pointer;
}

.fb-form__option:has(input:checked) {
  border-color: var(--brand);
  background: var(--brand-soft);
}

.fb-form__comment {
  display: grid;
}

.fb-form__comment textarea {
  resize: vertical;
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
  font-size: 13.5px;
}

.fb-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
