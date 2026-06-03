<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import type { Conversation } from '../types'
import ConversationMenu from './ConversationMenu.vue'

const props = defineProps<{ conversation: Conversation; active: boolean }>()
const emit = defineEmits<{
  select: []
  rename: [title: string]
  share: []
  delete: []
}>()

const editing = ref(false)
const draft = ref(props.conversation.title)
const inputRef = useTemplateRef<HTMLInputElement>('input')
const moreBtnRef = useTemplateRef<HTMLButtonElement>('moreBtn')
const menuOpen = ref(false)

const displayedTitle = ref(props.conversation.title)
const animating = ref(false)
let animationToken = 0
let mounted = false

const ERASE_SPEED = 22
const ERASE_PAUSE = 70
const WRITE_SPEED = 24

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

async function animateRewrite(target: string, token: number): Promise<void> {
  animating.value = true
  while (displayedTitle.value.length > 0 && token === animationToken) {
    displayedTitle.value = displayedTitle.value.slice(0, -1)
    await sleep(ERASE_SPEED)
  }
  if (token !== animationToken) return
  await sleep(ERASE_PAUSE)
  for (let i = 1; i <= target.length; i++) {
    if (token !== animationToken) return
    displayedTitle.value = target.slice(0, i)
    await sleep(WRITE_SPEED)
  }
  if (token === animationToken) animating.value = false
}

watch(
  () => props.conversation.title,
  async (next) => {
    if (!editing.value) draft.value = next
    if (!mounted || editing.value) {
      displayedTitle.value = next
      return
    }
    if (next === displayedTitle.value) return
    const token = ++animationToken
    await animateRewrite(next, token)
  },
)

onMounted(() => {
  mounted = true
})

onUnmounted(() => {
  animationToken++
})

const time = computed(() => {
  const d = new Date(props.conversation.updated_at)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'ahora'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'ayer'
  if (days < 7) return `${days}d`
  return d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })
})

async function startEdit(): Promise<void> {
  animationToken++
  animating.value = false
  displayedTitle.value = props.conversation.title
  editing.value = true
  draft.value = props.conversation.title
  await nextTick()
  const el = inputRef.value
  if (el) {
    el.focus()
    el.select()
  }
}

function commit(): void {
  const next = draft.value.trim()
  if (!next || next === props.conversation.title) {
    editing.value = false
    draft.value = props.conversation.title
    return
  }
  displayedTitle.value = next
  editing.value = false
  emit('rename', next)
}

function cancel(): void {
  draft.value = props.conversation.title
  editing.value = false
}

function onClick(): void {
  if (editing.value || menuOpen.value) return
  emit('select')
}

function toggleMenu(e: Event): void {
  e.stopPropagation()
  menuOpen.value = !menuOpen.value
}
</script>

<template>
  <div
    class="item-wrap"
    :class="{
      'item-wrap--active': active,
      'item-wrap--editing': editing,
      'item-wrap--animating': animating,
      'item-wrap--menu-open': menuOpen,
    }"
  >
    <button type="button" class="item" :disabled="editing" @click="onClick">
      <span class="item__main">
        <input
          v-if="editing"
          ref="input"
          v-model="draft"
          class="item__input"
          maxlength="200"
          @keydown.enter.prevent="commit"
          @keydown.esc.prevent="cancel"
          @blur="commit"
          @click.stop
        />
        <template v-else>
          <span class="item__title">
            {{ displayedTitle }}<span v-if="animating" class="item__caret" aria-hidden="true" />
          </span>
        </template>
        <svg
          v-if="conversation.title_locked && !editing && !animating"
          class="item__lock"
          width="11"
          height="11"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-label="Título fijado"
        >
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      </span>
      <span v-if="!editing && !menuOpen" class="item__time">{{ time }}</span>
    </button>

    <div v-if="!editing" class="item__action-slot">
      <Tooltip v-if="!menuOpen" text="Más opciones" side="right">
        <button
          ref="moreBtn"
          type="button"
          class="item__more"
          :class="{ 'item__more--open': menuOpen }"
          aria-label="Más opciones"
          :aria-expanded="menuOpen"
          @click="toggleMenu"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="6" r="1.5" />
            <circle cx="12" cy="12" r="1.5" />
            <circle cx="12" cy="18" r="1.5" />
          </svg>
        </button>
      </Tooltip>
      <button
        v-else
        ref="moreBtn"
        type="button"
        class="item__more item__more--open"
        aria-label="Más opciones"
        :aria-expanded="menuOpen"
        @click="toggleMenu"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="6" r="1.5" />
          <circle cx="12" cy="12" r="1.5" />
          <circle cx="12" cy="18" r="1.5" />
        </svg>
      </button>

      <ConversationMenu
        :open="menuOpen"
        :anchor="moreBtnRef"
        @update:open="menuOpen = $event"
        @rename="startEdit"
        @share="emit('share')"
        @delete="emit('delete')"
      />
    </div>
  </div>
</template>

<style scoped>
.item-wrap {
  position: relative;
  display: flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 7px;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.item-wrap:hover {
  background: var(--surface-subtle);
}

.item-wrap--active {
  background: var(--surface-elev);
  border-color: var(--border);
  box-shadow: var(--shadow-xs);
}

.item-wrap--editing {
  background: var(--surface-elev);
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-ring);
}

.item-wrap--animating {
  background: var(--surface-elev);
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-ring);
  animation: rewrite-glow 1.6s ease-out infinite;
}

@keyframes rewrite-glow {
  0%,
  100% {
    box-shadow: 0 0 0 2px var(--brand-ring);
  }
  50% {
    box-shadow: 0 0 0 4px var(--brand-ring);
  }
}

.item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-width: 0;
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 13px;
  font-weight: var(--fw-regular);
  transition: color var(--duration-fast) var(--ease-out);
}

.item:hover {
  color: var(--text);
}

.item:disabled {
  cursor: default;
}

.item-wrap--active .item,
.item-wrap--animating .item {
  color: var(--text);
}

.item__main {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  flex: 1;
}

.item__title {
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--fw-medium);
  letter-spacing: -0.005em;
  min-width: 0;
  flex: 1;
}

.item__caret {
  display: inline-block;
  width: 2px;
  height: 0.95em;
  margin-left: 2px;
  background: var(--brand);
  animation: caret-blink 0.7s step-end infinite;
  flex-shrink: 0;
}

@keyframes caret-blink {
  50% {
    opacity: 0;
  }
}

.item__lock {
  flex-shrink: 0;
  color: var(--text-subtle);
}

.item__input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  padding: 0;
  font: inherit;
  color: var(--text);
  font-weight: var(--fw-medium);
}

.item__time {
  flex-shrink: 0;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-subtle);
  letter-spacing: 0.02em;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.item-wrap--animating .item__time {
  opacity: 0;
}

.item__action-slot {
  position: absolute;
  right: var(--space-2);
  top: 50%;
  transform: translateY(-50%);
}

.item__more {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transform: scale(0.92);
  transition: all var(--duration-fast) var(--ease-out);
}

.item-wrap:hover:not(.item-wrap--animating) .item__more,
.item__more--open {
  opacity: 1;
  transform: scale(1);
}

.item-wrap:hover:not(.item-wrap--animating) .item__time,
.item-wrap--menu-open .item__time {
  opacity: 0;
}

.item__more:hover,
.item__more--open {
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--border-strong);
}

@media (hover: none) {
  .item__more {
    opacity: 1;
    transform: scale(1);
    background: transparent;
    border-color: transparent;
  }
  .item-wrap:hover .item__time {
    opacity: 1;
  }
}
</style>
