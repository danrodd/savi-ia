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
const stickToBottom = ref(true)
const SCROLL_THRESHOLD = 80

function onScroll(): void {
  const el = container.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = distance <= SCROLL_THRESHOLD
}

watch(
  () => props.messages.map((m) => `${m.text.length}:${m.toolCalls.length}:${m.done}`).join('|'),
  () => {
    if (!stickToBottom.value) return
    nextTick(() => {
      const el = container.value
      if (el) el.scrollTop = el.scrollHeight
    })
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
