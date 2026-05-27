<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBreakpoint } from '@/composables/useBreakpoint'
import BrandMark from '../components/BrandMark.vue'
import Composer from '../components/Composer.vue'
import MessageList from '../components/MessageList.vue'
import MobileTopBar from '../components/MobileTopBar.vue'
import Sidebar from '../components/Sidebar.vue'
import { useChatStore } from '../stores/chatStore'

const route = useRoute()
const router = useRouter()
const store = useChatStore()
const {
  conversations,
  activeConversation,
  activeConversationId,
  messages,
  loadingConversations,
  streaming,
  error,
} = storeToRefs(store)

const { isMobile } = useBreakpoint()
const sidebarOpen = ref(false)
const sidebarVisible = computed(() => (isMobile.value ? sidebarOpen.value : true))

async function syncWithRoute(id: string | undefined): Promise<void> {
  if (id && id !== activeConversationId.value) {
    await store.loadConversation(id)
  } else if (!id && activeConversationId.value !== null) {
    store.clearActive()
  }
}

onMounted(async () => {
  await store.loadConversations()
  const routeId = route.params.id as string | undefined
  if (routeId) await store.loadConversation(routeId)
})

watch(
  () => route.params.id,
  (id) => syncWithRoute(id as string | undefined),
)

watch(isMobile, (mobile) => {
  if (!mobile) sidebarOpen.value = false
})

function handleSelect(id: string): void {
  if (id !== activeConversationId.value) {
    router.push({ name: 'conversation', params: { id } })
  }
  if (isMobile.value) sidebarOpen.value = false
}

function handleNewChat(): void {
  if (route.name !== 'home') router.push({ name: 'home' })
  store.clearActive()
  if (isMobile.value) sidebarOpen.value = false
}

async function handleSend(text: string): Promise<void> {
  const wasNew = !activeConversationId.value
  await store.sendMessage(text)
  if (wasNew && activeConversationId.value) {
    router.replace({ name: 'conversation', params: { id: activeConversationId.value } })
  }
}
</script>

<template>
  <div class="chat-shell">
    <Sidebar
      :conversations="conversations"
      :active-id="activeConversationId"
      :loading="loadingConversations"
      :open="sidebarVisible"
      :mobile="isMobile"
      @select="handleSelect"
      @new-chat="handleNewChat"
      @close="sidebarOpen = false"
    />

    <main class="chat-main">
      <MobileTopBar
        v-if="isMobile"
        :title="activeConversation?.title ?? 'SAVI'"
        @menu-open="sidebarOpen = true"
        @new-chat="handleNewChat"
      />

      <div v-if="error" class="chat-main__banner" role="alert">{{ error }}</div>

      <div v-if="messages.length === 0" class="empty">
        <div class="empty__inner">
          <BrandMark :size="72" label="S" class="empty__mark" />
          <p class="empty__eyebrow">SEO ERP</p>
          <h1 class="empty__title">Hola, soy SAVI</h1>
          <p class="empty__tagline">
            Tu <em>asistente virtual inteligente</em> del ERP.
          </p>
          <p class="empty__hint">
            Pregúntame sobre los datos de tu empresa, módulos del sistema o cómo usar SAVI.
          </p>
        </div>
      </div>

      <MessageList v-else :messages="messages" />

      <Composer :streaming="streaming" @send="handleSend" @stop="store.stopStream" />
    </main>
  </div>
</template>

<style scoped>
.chat-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) 1fr;
  height: 100%;
  background: var(--surface);
  overflow: hidden;
}

@media (max-width: 767px) {
  .chat-shell {
    grid-template-columns: 1fr;
  }
}

.chat-main {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.chat-main__banner {
  padding: var(--space-3) var(--space-5);
  background: var(--brand-soft);
  border-bottom: 1px solid var(--brand);
  color: var(--brand);
  font-size: 13px;
  font-weight: var(--fw-medium);
  flex-shrink: 0;
}

.empty {
  flex: 1;
  min-height: 0;
  display: grid;
  place-items: center;
  padding: var(--space-7) var(--space-5);
  text-align: center;
  overflow-y: auto;
}

.empty__inner {
  max-width: 480px;
}

.empty__mark {
  margin: 0 auto var(--space-7);
  box-shadow: var(--shadow-brand);
}

.empty__mark :deep(.brand-mark__glyph) {
  font-size: 40px;
}

.empty__eyebrow {
  margin: 0 0 var(--space-3);
  font-size: 11px;
  font-weight: var(--fw-semibold);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--text-subtle);
}

.empty__title {
  margin: 0 0 var(--space-3);
  font-family: var(--font-display);
  font-size: clamp(28px, 6vw, 40px);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.1;
}

.empty__tagline {
  margin: 0 auto var(--space-4);
  font-family: var(--font-serif);
  font-size: clamp(17px, 3.5vw, 22px);
  font-style: italic;
  font-weight: var(--fw-regular);
  line-height: 1.4;
  color: var(--text-muted);
  letter-spacing: -0.005em;
  max-width: 380px;
}

.empty__tagline em {
  font-style: italic;
  color: var(--brand);
}

.empty__hint {
  margin: 0 auto;
  max-width: 380px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--text-subtle);
}

@media (max-width: 767px) {
  .empty {
    padding: var(--space-5);
  }

  .empty__mark {
    width: 56px !important;
    height: 56px !important;
    margin-bottom: var(--space-5);
  }

  .empty__mark :deep(.brand-mark__glyph) {
    font-size: 30px;
  }
}
</style>
