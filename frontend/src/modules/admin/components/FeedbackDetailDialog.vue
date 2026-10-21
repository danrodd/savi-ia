<script setup lang="ts">
import { Dialog } from '@savi/ui'
import { computed } from 'vue'
import { formatFullDateTime } from '@/lib/dateTime'
import { toast } from '@/lib/toast'
import MarkdownRenderer from '@/modules/chat/components/MarkdownRenderer.vue'
import type { FeedbackItem } from '../types'
import { FEEDBACK_RATING_LABELS, FEEDBACK_REASON_LABELS } from '../utils/feedback'

const props = defineProps<{ open: boolean; item: FeedbackItem | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const who = computed(() => {
  const i = props.item
  if (!i) return ''
  return (
    [i.user_name, i.user_login ? `(${i.user_login})` : null].filter(Boolean).join(' ') ||
    `#${i.user_id}`
  )
})

async function copyConversationId(): Promise<void> {
  if (!props.item) return
  try {
    await navigator.clipboard.writeText(props.item.conversation_id)
    toast.success('Copiamos el identificador de la conversación.')
  } catch {
    toast.error('No pudimos copiarlo. Selecciónelo y cópielo a mano.')
  }
}
</script>

<template>
  <Dialog
    :open="open"
    title="Detalle de la calificación"
    :max-width="760"
    @update:open="emit('update:open', $event)"
  >
    <div v-if="item" class="fdetail" data-testid="feedback-detail">
      <p class="fdetail__meta">
        <span class="fdetail__badge" :class="`fdetail__badge--${item.rating}`">
          {{ FEEDBACK_RATING_LABELS[item.rating] }}
        </span>
        <span v-if="item.reason">{{ FEEDBACK_REASON_LABELS[item.reason] }}</span>
        <span>{{ who }}</span>
        <span>{{ formatFullDateTime(item.created_at) }}</span>
      </p>

      <section v-if="item.comment">
        <h3 class="fdetail__h">Comentario</h3>
        <p class="fdetail__comment">{{ item.comment }}</p>
      </section>

      <section>
        <h3 class="fdetail__h">Pregunta</h3>
        <p class="fdetail__question">{{ item.question ?? '—' }}</p>
      </section>

      <section>
        <h3 class="fdetail__h">Respuesta</h3>
        <div class="fdetail__answer"><MarkdownRenderer :source="item.answer" /></div>
      </section>

      <dl class="fdetail__facts">
        <div><dt>Proveedor</dt><dd>{{ item.provider ?? '—' }}</dd></div>
        <div><dt>Modelo</dt><dd>{{ item.model ?? '—' }}</dd></div>
        <div>
          <dt>Costo</dt>
          <dd>{{ item.cost_usd === null ? '—' : `US$ ${item.cost_usd.toFixed(4)}` }}</dd>
        </div>
        <div><dt>Base</dt><dd>{{ item.database_code ?? '—' }}</dd></div>
        <div class="fdetail__wide">
          <dt>Consultas usadas</dt>
          <dd>{{ item.tools.length ? item.tools.join(', ') : 'Ninguna' }}</dd>
        </div>
      </dl>

      <button type="button" class="fdetail__copy" @click="copyConversationId">
        Copiar ID de la conversación
      </button>
    </div>
  </Dialog>
</template>

<style scoped>
.fdetail {
  display: grid;
  gap: var(--space-5);
}

.fdetail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.fdetail__badge {
  padding: 2px var(--space-3);
  border-radius: var(--r-full, 999px);
  font-weight: var(--fw-semibold);
  background: var(--surface-subtle);
  color: var(--text);
}

.fdetail__badge--down {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.fdetail__h {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-subtle);
}

.fdetail__comment,
.fdetail__question {
  margin: 0;
  white-space: pre-wrap;
  font-size: 14px;
}

.fdetail__answer {
  max-height: 320px;
  overflow: auto;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
}

.fdetail__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.fdetail__facts dt {
  font-size: 11px;
  color: var(--text-subtle);
}

.fdetail__facts dd {
  margin: 0;
  font-size: 13px;
  word-break: break-word;
}

.fdetail__wide {
  grid-column: 1 / -1;
}

.fdetail__copy {
  justify-self: start;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
  color: var(--text);
  font-family: inherit;
  font-size: 12.5px;
  cursor: pointer;
}
</style>
