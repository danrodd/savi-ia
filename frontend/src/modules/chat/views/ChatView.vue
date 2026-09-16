<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { toast } from '@/lib/toast'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import Composer from '../components/Composer.vue'
import DatabasePicker from '../components/DatabasePicker.vue'
import MessageList from '../components/MessageList.vue'
import MobileTopBar from '../components/MobileTopBar.vue'
import ShareMenu from '../components/ShareMenu.vue'
import Sidebar from '../components/Sidebar.vue'
import WelcomeScreen from '../components/WelcomeScreen.vue'
import { buildConversationMarkdown, buildConversationUrl, tryWebShare } from '../lib/exportContent'
import { useChatStore } from '../stores/chatStore'
import type { Conversation } from '../types'

const route = useRoute()
const router = useRouter()
const store = useChatStore()
const authStore = useAuthStore()

// ── Modo "vista compartida" (ruta `/share/:id`) ────────────────────────
// Misma UI que /c/:id pero con un banner identificador. Cuando la
// conversación es del usuario actual, la vista queda editable (puede
// seguir conversando, regenerar, etc.). Cuando pertenece a otro usuario,
// se renderiza en modo read-only y se oculta el composer. Hoy el
// endpoint backend filtra por user_id (no devuelve conversaciones
// ajenas — 404), así que el caso "ajena" solo se va a poder ver cuando
// se habilite acceso público a nivel de backend. El frontend ya está
// preparado para ese día.
const isSharedRoute = computed(() => route.name === 'shared-conversation')
const isOwnedConversation = computed<boolean>(() => {
  const conv = activeConversation.value
  const me = authStore.user
  if (!conv || !me) return false
  if (conv.user_id === null) return false
  return String(conv.user_id) === String(me.id)
})
// En la ruta /share/:id, si la conversación NO es mía → solo lectura.
// En /c/:id nunca aplica read-only.
const isReadOnly = computed<boolean>(
  () => isSharedRoute.value && activeConversation.value !== null && !isOwnedConversation.value,
)
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
  availableDatabases,
  selectedDatabaseId,
  databaseNameById,
  activeDatabaseUnavailable,
  showsDatabaseContext,
} = storeToRefs(store)

const showsDatabasePicker = computed(
  () => activeConversationId.value === null && availableDatabases.value.length > 1,
)

const activeDatabaseName = computed<string | null>(() => {
  const id = activeConversation.value?.erp_database_id
  return id ? (databaseNameById.value.get(id) ?? null) : null
})

const conversationDatabaseLabels = computed<Record<string, string> | null>(() => {
  if (!showsDatabaseContext.value) return null
  const labels: Record<string, string> = {}
  for (const c of conversations.value) {
    const name = c.erp_database_id ? databaseNameById.value.get(c.erp_database_id) : undefined
    labels[c.id] = name && store.isDatabaseUsable(c.erp_database_id) ? name : 'Base no disponible'
  }
  return labels
})

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
  await Promise.all([store.loadConversations(), store.loadAvailableDatabases()])
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

function handleSend(text: string): void {
  // Sin `await`: la URL la mueve el watcher de abajo en cuanto existe la
  // conversación. Esperar al final del turno para navegar dejaba al usuario en
  // `/` durante toda la respuesta — y un F5 ahí perdía la conversación entera.
  void store.sendMessage(text)
}

watch(activeConversationId, (id) => {
  if (id && route.name === 'home') {
    router.replace({ name: 'conversation', params: { id } })
  }
})

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
      :database-labels="conversationDatabaseLabels"
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
        :share-content-el="showConversationShare ? conversationContentRef : undefined"
        @menu-open="sidebarOpen = true"
        @new-chat="handleNewChat"
      />

      <!-- Banner de "vista compartida". Dos variantes según la propiedad:
           - Mía: nota suave, sin restringir.
           - Ajena: aviso de solo lectura.
           El ShareMenu del thread completo se monta acá adentro (a la
           derecha) en lugar del botón flotante — así el header del banner
           y el botón quedan alineados visualmente, sin solapamiento. -->
      <div
        v-if="isSharedRoute && activeConversation"
        class="chat-main__share-banner"
        :class="{ 'chat-main__share-banner--readonly': isReadOnly }"
        role="status"
      >
        <div class="chat-main__share-banner-text">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          <span v-if="isReadOnly">
            Estás viendo una conversación compartida — <strong>solo lectura</strong>.
          </span>
          <span v-else>
            Esta conversación está compartida vía enlace. Vos sos el autor, podés seguir escribiendo normalmente.
          </span>
        </div>

        <ShareMenu
          v-if="showConversationShare && !isMobile"
          kind="conversation"
          placement="bottom-end"
          :text="conversationMarkdown"
          :conversation-id="activeConversationId"
          :content-el="conversationContentRef"
          :title="activeConversation?.title ?? 'Conversación con SAVI'"
        />
      </div>

      <div v-if="error" class="chat-main__banner" role="alert">{{ error }}</div>

      <div v-if="store.llmProviderUnavailable" class="chat-main__banner" role="alert">
        El asistente no está disponible en este momento. Contacta al administrador de SAVI.
        <RouterLink v-if="authStore.user?.is_admin" class="chat-main__admin-link" :to="{ name: 'admin-llm-providers' }">Ir a Proveedores de IA</RouterLink>
      </div>

      <div
        v-if="activeDatabaseUnavailable && !isReadOnly"
        class="chat-main__banner"
        role="alert"
      >
        La base de datos de esta conversación ya no está disponible. Puedes leer el historial,
        pero no enviar mensajes nuevos. Inicia una conversación nueva con otro cliente.
      </div>
      <div
        v-else-if="activeConversation && showsDatabaseContext && activeDatabaseName"
        class="chat-main__context"
      >
        <span class="chat-main__context-chip" title="La base de una conversación no se puede cambiar">
          Cliente: {{ activeDatabaseName }}
        </span>
      </div>

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
        :read-only="isReadOnly"
        @edit="handleEdit"
        @regenerate="handleRegenerate"
      />

      <!-- Share de conversación entera — botón flotante top-right.
           Solo se muestra cuando NO hay banner de vista compartida
           (en /share/:id el ShareMenu va integrado dentro del banner
           para evitar superposición visual). -->
      <Transition name="fade">
        <div
          v-if="showConversationShare && !isMobile && !isSharedRoute"
          class="chat-main__share"
        >
          <ShareMenu
            kind="conversation"
            placement="bottom-end"
            :text="conversationMarkdown"
            :conversation-id="activeConversationId"
            :content-el="conversationContentRef"
            :title="activeConversation?.title ?? 'Conversación con SAVI'"
          />
        </div>
      </Transition>

      <!-- Composer oculto en modo solo-lectura (vista compartida de una
           conversación ajena). Cuando es tuya, el composer aparece igual
           y podés seguir escribiendo aunque la URL sea /share/:id. -->
      <DatabasePicker
        v-if="showsDatabasePicker && !isReadOnly"
        v-model="selectedDatabaseId"
        :databases="availableDatabases"
      />

      <Composer
        v-if="!isReadOnly"
        :streaming="streaming"
        :disabled="activeDatabaseUnavailable || store.llmProviderUnavailable"
        :restore-text="store.rejectedText"
        @send="handleSend"
        @stop="() => void store.stopStream()"
        @restored="store.rejectedText = null"
      />
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
  background: radial-gradient(circle at 88% 0%, var(--brand-soft), transparent 28%), var(--surface);
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

.chat-main__admin-link { margin-left: var(--space-3); color: inherit; font-weight: var(--fw-semibold); text-decoration: underline; }

.chat-main__context {
  display: flex;
  justify-content: center;
  padding: var(--space-2) var(--space-5);
  flex-shrink: 0;
}

.chat-main__context-chip {
  padding: 3px var(--space-3);
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: var(--fw-medium);
}

.chat-main :deep(.welcome) { animation: workspace-in var(--duration-slow) var(--ease-out); }

@keyframes workspace-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* Banner identificador de "vista compartida". Variante suave por default
   (conversación propia), variante de alerta cuando es solo lectura.
   El layout es flex con la nota a la izquierda y el ShareMenu del
   thread a la derecha — así no necesitamos botón flotante en esta
   ruta y nada se superpone. */
.chat-main__share-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-5);
  background: var(--surface-elev);
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  flex-shrink: 0;
}

.chat-main__share-banner-text {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.chat-main__share-banner svg {
  flex-shrink: 0;
  color: var(--text-subtle);
}

.chat-main__share-banner strong {
  color: var(--text);
  font-weight: var(--fw-semibold);
}

.chat-main__share-banner--readonly {
  background: var(--brand-soft);
  border-bottom-color: var(--brand);
  color: var(--brand-strong, var(--brand));
}

.chat-main__share-banner--readonly svg,
.chat-main__share-banner--readonly strong {
  color: var(--brand);
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
