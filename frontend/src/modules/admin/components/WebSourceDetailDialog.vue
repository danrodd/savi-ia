<script setup lang="ts">
/**
 * Páginas de un sitio: qué se importó, qué se omitió y por qué.
 * Mientras el sitio se lee, el detalle se refresca solo.
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import Dialog from '@/components/ui/Dialog.vue'
import { useWebSourceStore, WEB_POLL_INTERVAL_MS } from '../stores/webSourceStore'
import type { WebPage, WebPageStatus, WebSourceDetail } from '../types'
import {
  hostOf,
  isWebInProgress,
  PAGE_STATUS_LABELS,
  pagesSummary,
  REFRESH_LABELS,
  sectionLabel,
  WEB_STATUS_LABELS,
} from '../utils/webSources'
import CompanyDocumentStatusBadge from './CompanyDocumentStatusBadge.vue'

const props = defineProps<{
  open: boolean
  sourceId: string | null
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

type PageFilter = 'all' | 'read' | 'problems'
const FILTERS: Record<PageFilter, { label: string; statuses: WebPageStatus[] }> = {
  all: { label: 'Todas', statuses: [] },
  read: { label: 'Leídas', statuses: ['imported', 'unchanged'] },
  problems: { label: 'Con problemas', statuses: ['failed', 'removed'] },
}

const store = useWebSourceStore()
const detail = ref<WebSourceDetail | null>(null)
const error = ref<string | null>(null)
const filter = ref<PageFilter>('all')
let timer: ReturnType<typeof setTimeout> | null = null

const dateFormatter = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : '—'
}

function stopTimer(): void {
  if (timer !== null) clearTimeout(timer)
  timer = null
}

async function load(): Promise<void> {
  stopTimer()
  if (!props.open || !props.sourceId) return
  try {
    detail.value = await store.getDetail(props.sourceId)
    error.value = null
  } catch (e) {
    error.value = (e as Error).message || 'No se pudo cargar el detalle.'
  }
  if (props.open && detail.value && isWebInProgress(detail.value.status)) {
    timer = setTimeout(() => void load(), WEB_POLL_INTERVAL_MS)
  }
}

watch(
  () => [props.open, props.sourceId] as const,
  ([open]) => {
    filter.value = 'all'
    if (open) {
      detail.value = null
      void load()
    } else {
      stopTimer()
    }
  },
  { immediate: true },
)

onUnmounted(stopTimer)

const counts = computed(() => {
  const pages = detail.value?.pages ?? []
  return Object.fromEntries(
    (Object.keys(FILTERS) as PageFilter[]).map((key) => [
      key,
      key === 'all'
        ? pages.length
        : pages.filter((p) => FILTERS[key].statuses.includes(p.status)).length,
    ]),
  ) as Record<PageFilter, number>
})

const visiblePages = computed<WebPage[]>(() => {
  const pages = detail.value?.pages ?? []
  if (filter.value === 'all') return pages
  return pages.filter((p) => FILTERS[filter.value].statuses.includes(p.status))
})

function pathOf(url: string): string {
  try {
    const parsed = new URL(url)
    return `${parsed.pathname}${parsed.search}${parsed.hash}` || '/'
  } catch {
    return url
  }
}
</script>

<template>
  <Dialog
    :open="open"
    :title="detail?.title ?? 'Sitio web'"
    :max-width="820"
    @update:open="emit('update:open', $event)"
  >
    <p v-if="error" class="wdetail__error" role="alert">{{ error }}</p>
    <p v-else-if="!detail" class="wdetail__hint">Cargando…</p>
    <div v-else class="wdetail">
      <div class="wdetail__summary">
        <a :href="detail.url" target="_blank" rel="noopener noreferrer" class="wdetail__url">
          {{ detail.mode === 'site' ? hostOf(detail.url) : detail.url }}
        </a>
        <CompanyDocumentStatusBadge
          :label="WEB_STATUS_LABELS[detail.status]"
          :message="detail.status_message"
        />
        <span class="wdetail__meta">{{ pagesSummary(detail) }}</span>
        <span class="wdetail__meta">Última lectura: {{ formatDate(detail.last_crawl_finished_at) }}</span>
        <span class="wdetail__meta">
          {{ REFRESH_LABELS[detail.refresh] }}
          <template v-if="detail.next_refresh_at">
            · próxima: {{ formatDate(detail.next_refresh_at) }}
          </template>
        </span>
      </div>
      <p
        v-if="detail.status_message"
        :class="detail.status === 'failed' ? 'wdetail__error' : 'wdetail__meta'"
      >{{ detail.status_message }}</p>
      <!-- Las omitidas no quedan en la lista: no tienen documento propio. -->
      <p v-if="detail.skipped_count" class="wdetail__meta">
        {{ detail.skipped_count === 1 ? 'Se omitió 1 página' : `Se omitieron ${detail.skipped_count} páginas` }}
        sin texto útil o iguales a otra página del sitio.
      </p>
      <p v-if="detail.excluded_sections.length" class="wdetail__meta">
        Secciones excluidas: {{ detail.excluded_sections.map(sectionLabel).join(', ') }}
      </p>

      <div v-if="detail.pages.length" class="wdetail__filters" role="tablist" aria-label="Filtrar páginas">
        <button
          v-for="(info, key) in FILTERS"
          :key="key"
          type="button"
          role="tab"
          class="wdetail__filter"
          :class="{ 'wdetail__filter--active': filter === key }"
          :aria-selected="filter === key"
          :disabled="counts[key] === 0 && key !== 'all'"
          @click="filter = key"
        >
          {{ info.label }} <span class="wdetail__count">{{ counts[key] }}</span>
        </button>
      </div>

      <p v-if="detail.pages.length === 0" class="wdetail__hint">
        {{ isWebInProgress(detail.status) ? 'Leyendo el sitio…' : 'No se leyó ninguna página.' }}
      </p>
      <ul v-else class="wdetail__pages">
        <li v-for="page in visiblePages" :key="page.document_id" class="wdetail__page">
          <div class="wdetail__page-main">
            <div class="wdetail__page-title">{{ page.title }}</div>
            <a :href="page.url" target="_blank" rel="noopener noreferrer" class="wdetail__page-url">
              {{ pathOf(page.url) }}
            </a>
            <div v-if="page.status_detail" class="wdetail__meta">{{ page.status_detail }}</div>
          </div>
          <div class="wdetail__page-state">
            <CompanyDocumentStatusBadge :label="PAGE_STATUS_LABELS[page.status]" />
            <span class="wdetail__meta">
              {{ page.last_changed_at ? `Cambió ${formatDate(page.last_changed_at)}` : '' }}
            </span>
          </div>
        </li>
      </ul>
    </div>
  </Dialog>
</template>

<style scoped>
.wdetail {
  display: grid;
  gap: var(--space-3);
}

.wdetail__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
}

.wdetail__url,
.wdetail__page-url {
  font-size: 12px;
  color: var(--brand, var(--text));
  overflow-wrap: anywhere;
}

.wdetail__meta {
  font-size: 12px;
  color: var(--text-muted);
}

.wdetail__hint {
  font-size: 13px;
  color: var(--text-muted);
}

.wdetail__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.wdetail__filters {
  display: inline-flex;
  flex-wrap: wrap;
  justify-self: start;
  gap: 2px;
  padding: 3px;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.wdetail__filter {
  padding: var(--space-1) var(--space-3);
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.wdetail__filter:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.wdetail__filter--active {
  background: var(--surface-elev);
  color: var(--text);
  box-shadow: var(--shadow-xs);
}

.wdetail__count {
  color: var(--text-subtle);
}

.wdetail__pages {
  display: grid;
  max-height: 55vh;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  list-style: none;
}

.wdetail__page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.wdetail__page:last-child {
  border-bottom: none;
}

.wdetail__page-title {
  font-weight: var(--fw-medium);
  overflow-wrap: anywhere;
}

.wdetail__page-state {
  display: grid;
  justify-items: end;
  align-content: start;
  gap: 2px;
}

@media (max-width: 620px) {
  .wdetail__page {
    grid-template-columns: 1fr;
  }

  .wdetail__page-state {
    justify-items: start;
  }
}
</style>
