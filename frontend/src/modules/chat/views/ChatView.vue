<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { toast } from '@/lib/toast'
import Composer from '../components/Composer.vue'
import MessageList from '../components/MessageList.vue'
import MobileTopBar from '../components/MobileTopBar.vue'
import ShareMenu from '../components/ShareMenu.vue'
import Sidebar from '../components/Sidebar.vue'
import WelcomeScreen from '../components/WelcomeScreen.vue'
import { buildConversationUrl, buildConversationMarkdown, tryWebShare } from '../lib/exportContent'
import { useChatStore } from '../stores/chatStore'
import type { Conversation } from '../types'

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
  lastUserIndex,
  canRegenerate,
  versionsByActiveId,
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

async function handleRename(id: string, title: string): Promise<void> {
  try {
    await store.renameConversation(id, title)
  } catch (e) {
    error.value = (e as Error).message
  }
}

const deleteTarget = ref<Conversation | null>(null)
const confirmDeleteOpen = computed({
  get: () => deleteTarget.value !== null,
  set: (open: boolean) => {
    if (!open) deleteTarget.value = null
  },
})

function requestDelete(id: string): void {
  deleteTarget.value = conversations.value.find((c) => c.id === id) ?? null
}

async function confirmDelete(): Promise<void> {
  const target = deleteTarget.value
  if (!target) return
  try {
    const { wasActive } = await store.deleteConversation(target.id)
    if (wasActive && route.name !== 'home') {
      router.replace({ name: 'home' })
    }
    toast.success('Conversación eliminada', { description: target.title })
  } catch (e) {
    toast.error('No se pudo eliminar la conversación', {
      description: (e as Error).message,
    })
  }
}

async function handleShare(id: string): Promise<void> {
  // Compartir desde el sidebar: acción rápida con el link de la conversación.
  // Decisión: NO replicar el menú de 5 opciones (HTML/PDF/MD) acá — eso
  // requeriría cargar los mensajes de una conversación que puede no estar
  // activa (pegándole al backend) y abrir un popover dentro de un popover.
  // Para el export completo el usuario abre la conversación y usa el
  // ShareMenu in-chat. Acá: Web Share nativo con el link; fallback copy.
  const link = buildConversationUrl(id)
  const target = conversations.value.find((c) => c.id === id)
  const title = target?.title ?? 'Conversación con SAVI'
  const ok = await tryWebShare({ title, url: link })
  if (ok) return
  try {
    await navigator.clipboard.writeText(link)
    toast.success('Enlace copiado')
  } catch {
    toast.error('No se pudo compartir')
  }
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

function handleEdit(text: string): void {
  store.editLastUserMessage(text)
}

function handleRegenerate(): void {
  store.regenerateLastAssistant()
}

// ── Share/Download de la conversación completa ────────────────────────
// Tomamos el DOM del MessageList para HTML/PDF (preserva el render que
// el usuario está viendo) y armamos un markdown serializado desde los
// datos para .md (más fiel que recolectar HTML y convertirlo de vuelta).
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
const conversationContentRef = computed<HTMLElement | null>(
  () => messageListRef.value?.container ?? null,
)
const conversationMarkdown = computed<string>(() =>
  buildConversationMarkdown(messages.value, activeConversation.value?.title ?? 'Conversación'),
)
const showConversationShare = computed<boolean>(
  () => activeConversationId.value !== null && messages.value.length > 0,
)
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
      @rename="handleRename"
      @share="handleShare"
      @delete="requestDelete"
      @new-chat="handleNewChat"
      @close="sidebarOpen = false"
    />

    <main class="chat-main">
      <MobileTopBar
        v-if="isMobile"
        :title="activeConversation?.title ?? 'SAVI'"
        :share-text="showConversationShare ? conversationMarkdown : undefined"
        :share-conversation-id="activeConversationId"
        :share-content-ref="showConversationShare ? conversationContentRef : undefined"
        @menu-open="sidebarOpen = true"
        @new-chat="handleNewChat"
      />

      <div v-if="error" class="chat-main__banner" role="alert">{{ error }}</div>

      <WelcomeScreen v-if="messages.length === 0" @suggest="handleSend" />

      <MessageList
        v-else
        ref="messageListRef"
        :messages="messages"
        :last-user-index="lastUserIndex"
        :can-regenerate="canRegenerate"
        :streaming="streaming"
        :versions-by-active-id="versionsByActiveId"
        :conversation-id="activeConversationId"
        @edit="handleEdit"
        @regenerate="handleRegenerate"
      />

      <!-- Share de conversación entera — botón flotante top-right.
           Decisión: ubicarlo acá (in-chat) y NO solo en el ConversationMenu
           del sidebar para que sea discoverable sin tener que hovear los
           tres puntos de cada item. Se muestra solo cuando hay mensajes
           Y la conversación ya está persistida (tiene id). -->
      <Transition name="fade">
        <div v-if="showConversationShare && !isMobile" class="chat-main__share">
          <ShareMenu
            kind="conversation"
            placement="bottom-end"
            :text="conversationMarkdown"
            :conversation-id="activeConversationId"
            :content-ref="conversationContentRef"
            :title="activeConversation?.title ?? 'Conversación con SAVI'"
          />
        </div>
      </Transition>

      <Composer :streaming="streaming" @send="handleSend" @stop="store.stopStream" />
    </main>

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="Eliminar conversación"
      :description="
        deleteTarget
          ? `Se eliminará “${deleteTarget.title}”. Esta acción no se puede deshacer.`
          : ''
      "
      confirm-label="Eliminar"
      variant="danger"
      :on-confirm="confirmDelete"
    />
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

/* Botón flotante de "compartir conversación" en desktop. Se posiciona
   sobre la lista de mensajes pero sin tapar el contenido (top-right). */
.chat-main__share {
  position: absolute;
  top: var(--space-4);
  right: var(--space-5);
  z-index: 10;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
}

.chat-main__share :deep(.share-menu__trigger) {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--text-muted);
}

.chat-main__share :deep(.share-menu__trigger:hover) {
  background: var(--surface-hover);
  color: var(--text);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

</style>
