<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { MessageVersion, UIMessage } from '../types'
import AssistantMessage from './AssistantMessage.vue'
import UserMessage from './UserMessage.vue'

const props = defineProps<{
  messages: UIMessage[]
  lastUserIndex: number
  canRegenerate: boolean
  streaming: boolean
  versionsByActiveId: Record<string, MessageVersion[]>
}>()
const emit = defineEmits<{
  edit: [text: string]
  regenerate: []
}>()

const container = ref<HTMLDivElement | null>(null)

/**
 * Autoscroll inteligente — patrón estándar de chats (ChatGPT/Slack):
 *
 * - **Carga inicial / cambio de conversación**: scroll instant al fondo.
 *   Sin animación, sin parpadeo "veo el inicio y después salta".
 * - **Mensaje nuevo del usuario**: scroll al fondo SIEMPRE. El usuario
 *   acaba de mandarlo: querés ver tu propio mensaje y la respuesta.
 * - **Stream del asistente**: scrolea solo si el usuario está cerca del
 *   fondo (`stickToBottom`). Si está arriba leyendo algo viejo, no se le
 *   roba el foco.
 * - **Usuario scrollea arriba**: `stickToBottom = false`. El stream deja
 *   de seguirlo automáticamente hasta que vuelva al fondo (≤ THRESHOLD).
 */
const SCROLL_THRESHOLD = 80
const stickToBottom = ref(true)
let programmaticScroll = false

function scrollToBottom(): void {
  const el = container.value
  if (!el) return
  programmaticScroll = true
  el.scrollTop = el.scrollHeight
  // Liberamos el flag tras dos frames: el evento `scroll` que dispara
  // este `scrollTop` corre asíncrono y queremos que no actualice
  // `stickToBottom` cuando es un scroll que nosotros forzamos.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      programmaticScroll = false
    })
  })
}

function onScroll(): void {
  if (programmaticScroll) return
  const el = container.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = distance <= SCROLL_THRESHOLD
}

// Watch #1: cambios de "estructura" (carga inicial, switch, mensaje nuevo).
// Decide si forzamos scroll independientemente de `stickToBottom`.
watch(
  () => ({
    length: props.messages.length,
    firstId: props.messages[0]?.tempId,
    lastRole: props.messages[props.messages.length - 1]?.role,
  }),
  (curr, prev) => {
    const prevLen = prev?.length ?? 0
    const conversationChanged = curr.firstId !== prev?.firstId
    const messageAdded = curr.length > prevLen
    if (curr.length === 0) return

    // Carga inicial o cambio de conversación → al fondo, ya.
    if (conversationChanged || prev === undefined) {
      stickToBottom.value = true
      // Doble nextTick: el primero deja que Vue renderice el DOM;
      // el segundo espera a que el navegador calcule scrollHeight con
      // las alturas reales de los mensajes (importante con markdown
      // pesado, tablas, code blocks…).
      nextTick(() => nextTick(() => scrollToBottom()))
      return
    }

    // Mensaje nuevo del usuario → al fondo SIEMPRE.
    // (`messageAdded && lastRole === 'user'` ignora el caso de stream del
    //  asistente que se maneja en el watch #2.)
    if (messageAdded && curr.lastRole === 'user') {
      stickToBottom.value = true
      nextTick(() => scrollToBottom())
    }
  },
  { immediate: true },
)

// Watch #2: cambios de contenido del último mensaje (stream del asistente).
// Solo scrolea si el usuario está cerca del fondo.
watch(
  () => props.messages.map((m) => `${m.text.length}:${m.toolCalls.length}:${m.done}`).join('|'),
  () => {
    if (!stickToBottom.value) return
    nextTick(() => scrollToBottom())
  },
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
</script>

<template>
  <div ref="container" class="message-list" @scroll="onScroll">
    <div class="message-list__inner">
      <template v-for="(m, i) in messages" :key="m.tempId">
        <UserMessage
          v-if="m.role === 'user'"
          :text="m.text"
          :message-id="m.id"
          :can-edit="i === lastUserIndex && !streaming"
          :versions="versionsFor(m.id)"
          @edit="(text) => emit('edit', text)"
        />
        <AssistantMessage
          v-else
          :message="m"
          :can-regenerate="isLastDoneAssistant(i) && canRegenerate"
          :versions="versionsFor(m.id)"
          @regenerate="emit('regenerate')"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
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

@media (max-width: 767px) {
  .message-list {
    padding: 56px var(--space-4) var(--space-5);
  }
}
</style>
