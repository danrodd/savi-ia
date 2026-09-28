<script setup lang="ts">
/**
 * "Fuentes" debajo de una respuesta: los documentos de la empresa citados.
 *
 * Una página web se abre con su link público: no pasa por el backend ni
 * necesita token, y sirve también en la vista compartida.
 *
 * Abrir el original pasa por `HttpClient` (con el token) y se muestra como
 * blob: un `<a href>` directo no llevaría la autenticación. El backend
 * responde 404 ante cualquier falta de permiso; en ese caso la fuente se
 * marca como no disponible en la vista.
 */
import { ref } from 'vue'

import { HttpClient, HttpRequestError } from '@/lib/HttpClient'
import { toast } from '@/lib/toast'
import type { MessageSource } from '../types'
import { toSuperscript, webSourceLink } from '../utils/citations'

const props = defineProps<{
  sources: MessageSource[]
  conversationId: string | null
  /** Vista compartida de una conversación ajena: se listan, no se abren. */
  readOnly: boolean
}>()

const http = new HttpClient('/company-documents')
const opening = ref<string | null>(null)
const lostAccess = ref<Set<string>>(new Set())

const REVOKE_AFTER_MS = 60_000

function isAvailable(source: MessageSource): boolean {
  return source.available !== false && !lostAccess.value.has(source.document_id)
}

function unavailableLabel(source: MessageSource): string {
  if (lostAccess.value.has(source.document_id)) return 'no disponible'
  if (source.unavailable_reason === 'deleted') return 'eliminado'
  if (source.unavailable_reason === 'processing') return 'actualizándose'
  return 'no disponible'
}

function canOpen(source: MessageSource): boolean {
  return !props.readOnly && props.conversationId !== null && isAvailable(source)
}

function firstPage(pages: string | null): string | null {
  const match = pages?.match(/^\d+/)
  return match ? match[0] : null
}

async function open(source: MessageSource): Promise<void> {
  if (!canOpen(source) || props.conversationId === null) return
  opening.value = source.document_id
  try {
    const blob = await http.getBlob(`/${source.document_id}/file`, {
      query: { conversation_id: props.conversationId },
    })
    const page = firstPage(source.pages)
    const url = URL.createObjectURL(blob)
    window.open(page ? `${url}#page=${page}` : url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS)
  } catch (error) {
    if (error instanceof HttpRequestError && error.status === 404) {
      lostAccess.value = new Set([...lostAccess.value, source.document_id])
      toast.error('Este documento ya no está disponible para ti.')
    } else {
      toast.error('No se pudo abrir el documento.')
    }
  } finally {
    opening.value = null
  }
}
</script>

<template>
  <div class="sources">
    <p class="sources__title">Fuentes</p>
    <ol class="sources__list">
      <li v-for="(source, index) in sources" :key="source.document_id" class="sources__item">
        <span class="sources__number" aria-hidden="true">{{ toSuperscript(index + 1) }}</span>
        <a
          v-if="webSourceLink(source.url) && isAvailable(source)"
          class="sources__link"
          :href="webSourceLink(source.url)?.href"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="`Abrir ${source.title} en ${webSourceLink(source.url)?.host}`"
        >
          {{ source.title }}
        </a>
        <button
          v-else-if="canOpen(source)"
          type="button"
          class="sources__link"
          :disabled="opening === source.document_id"
          :aria-label="`Abrir ${source.title}${source.pages ? `, páginas ${source.pages}` : ''}`"
          @click="open(source)"
        >
          {{ source.title }}
        </button>
        <span v-else class="sources__name" :class="{ 'sources__name--off': !isAvailable(source) }">
          {{ source.title }}
        </span>
        <span v-if="webSourceLink(source.url)" class="sources__meta">
          · {{ webSourceLink(source.url)?.host }}
        </span>
        <span v-if="source.pages" class="sources__meta">· p. {{ source.pages }}</span>
        <span v-if="!isAvailable(source)" class="sources__meta">({{ unavailableLabel(source) }})</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.sources {
  margin-top: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
}

.sources__title {
  margin: 0 0 var(--space-1);
  font-size: 11px;
  font-weight: var(--fw-medium);
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.sources__list {
  display: grid;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.sources__item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1);
  font-size: 13px;
}

.sources__number {
  min-width: 1ch;
  color: var(--text-muted);
}

.sources__link {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--brand-strong);
  font: inherit;
  text-align: left;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.sources__link:disabled {
  cursor: progress;
  opacity: 0.6;
}

.sources__link:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.sources__name {
  color: var(--text);
}

.sources__name--off {
  color: var(--text-muted);
}

.sources__meta {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
