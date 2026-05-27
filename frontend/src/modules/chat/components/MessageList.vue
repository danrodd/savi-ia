<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { UIMessage } from '../types'
import AssistantMessage from './AssistantMessage.vue'
import UserMessage from './UserMessage.vue'

const props = defineProps<{ messages: UIMessage[] }>()

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
</script>

<template>
  <div ref="container" class="message-list" @scroll="onScroll">
    <div class="message-list__inner">
      <template v-for="(m, i) in messages" :key="i">
        <UserMessage v-if="m.role === 'user'" :text="m.text" />
        <AssistantMessage v-else :message="m" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-7) var(--space-7) var(--space-7);
}

.message-list__inner {
  max-width: var(--content-max-width);
  margin: 0 auto;
}

@media (max-width: 767px) {
  .message-list {
    padding: var(--space-5) var(--space-4) var(--space-5);
  }
}
</style>
