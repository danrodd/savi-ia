<script setup lang="ts">
import { ref } from 'vue'
import { useAutoScroll } from '../composables/useAutoScroll'
import type { MessageVersion, UIAttachment, UIMessage } from '../types'
import AssistantMessage from './AssistantMessage.vue'
import ScrollToBottomButton from './ScrollToBottomButton.vue'
import UserMessage from './UserMessage.vue'

const props = withDefaults(
  defineProps<{
    messages: UIMessage[]
    lastUserIndex: number
    canRegenerate: boolean
    streaming: boolean
    versionsByActiveId: Record<string, MessageVersion[]>
    /** ID de la conversación activa — se propaga al ShareMenu de cada mensaje. */
    conversationId: string | null
    /** Modo solo-lectura (vista compartida): sin editar ni regenerar. */
    readOnly?: boolean
  }>(),
  { readOnly: false },
)
const emit = defineEmits<{
  edit: [text: string, attachments: UIAttachment[]]
  regenerate: []
}>()

const container = ref<HTMLDivElement | null>(null)

const { stickToBottom, hasNewContent, jumpToBottom } = useAutoScroll(
  container,
  () => props.messages,
)

function versionsFor(id: string | null): MessageVersion[] | null {
  if (!id) return null
  return props.versionsByActiveId[id] ?? null
}

function isLastDoneAssistant(idx: number): boolean {
  if (props.streaming) return false
  for (let i = props.messages.length - 1; i >= 0; i--) {
    const m = props.messages[i]
    if (!m) continue
    if (m.role === 'assistant' && m.done) return i === idx
    if (m.role === 'user') return false
  }
  return false
}

// Exponemos el container hacia ChatView para que ShareMenu pueda exportar
// la conversación completa a HTML/PDF (necesita el outerHTML del listado).
defineExpose({ container })
</script>

<template>
  <div class="message-list-wrap">
    <div ref="container" class="message-list">
      <div class="message-list__inner">
        <template v-for="(m, i) in messages" :key="m.tempId">
          <UserMessage
            v-if="m.role === 'user'"
            :text="m.text"
            :message-id="m.id"
            :can-edit="!readOnly && i === lastUserIndex && !streaming"
            :versions="versionsFor(m.id)"
            :attachments="m.attachments ?? []"
            @edit="(text, attachments) => emit('edit', text, attachments)"
          />
          <AssistantMessage
            v-else
            :message="m"
            :can-regenerate="!readOnly && isLastDoneAssistant(i) && canRegenerate"
            :versions="versionsFor(m.id)"
            :conversation-id="conversationId"
            :read-only="readOnly"
            @regenerate="emit('regenerate')"
          />
        </template>
      </div>
    </div>

    <Transition name="scroll-btn">
      <ScrollToBottomButton
        v-if="!stickToBottom"
        class="message-list__scroll-btn"
        :has-new="hasNewContent"
        :streaming="streaming"
        @click="jumpToBottom"
      />
    </Transition>
  </div>
</template>

<style scoped>
.message-list-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 72px var(--space-7) var(--space-7);
}

.message-list__inner {
  max-width: var(--content-max-width);
  margin: 0 auto;
}

/* Centrado horizontal sin `transform` para no chocar con el hover/transición
   del propio botón (ambos usan transform y se pisarían). */
.message-list__scroll-btn {
  position: absolute;
  bottom: var(--space-4);
  left: 0;
  right: 0;
  margin-inline: auto;
  width: max-content;
  z-index: 2;
}

/* Transición de entrada/salida del botón flotante. La entrada es lenta y con
   leve escala para que "crezca" suave; la salida, algo más ágil. */
.scroll-btn-enter-active {
  transition:
    opacity var(--duration-slow) var(--ease-out),
    transform var(--duration-slow) var(--ease-out);
}

.scroll-btn-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-out);
}

.scroll-btn-enter-from,
.scroll-btn-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.92);
}

@media (prefers-reduced-motion: reduce) {
  .scroll-btn-enter-active,
  .scroll-btn-leave-active {
    transition: opacity var(--duration-fast) var(--ease-out);
  }

  .scroll-btn-enter-from,
  .scroll-btn-leave-to {
    transform: none;
  }
}

@media (max-width: 767px) {
  .message-list {
    padding: 56px var(--space-4) var(--space-5);
  }
}
</style>
