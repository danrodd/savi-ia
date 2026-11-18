<script setup lang="ts">
/**
 * Archivo que SAVI generó para la respuesta (Excel, PDF, CSV o Word).
 * Se descarga del servidor con la sesión del usuario: solo el dueño puede.
 */
import { computed, ref } from 'vue'
import { triggerDownload } from '@/lib/download'
import { HttpClient, HttpRequestError } from '@/lib/HttpClient'
import type { GeneratedFileRef } from '../types'
import { fileKindLabel, fileSizeLabel } from '../utils/files'

const props = defineProps<{ file: GeneratedFileRef }>()

const http = new HttpClient('/files')
const downloading = ref(false)
const error = ref<string | null>(null)

const kind = computed(() => fileKindLabel(props.file.filename))
const size = computed(() => fileSizeLabel(props.file.size_bytes))

async function download(): Promise<void> {
  downloading.value = true
  error.value = null
  try {
    const blob = await http.getBlob(`/${props.file.id}`)
    const url = URL.createObjectURL(blob)
    triggerDownload(url, props.file.filename)
    setTimeout(() => URL.revokeObjectURL(url), 0)
  } catch (e) {
    error.value =
      e instanceof HttpRequestError && e.status === 404
        ? 'Este archivo ya no está disponible. Pídalo de nuevo.'
        : 'No se pudo descargar el archivo. Intente de nuevo.'
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <div class="file-card" data-testid="file-card">
    <span class="file-card__badge" :class="`file-card__badge--${kind.toLowerCase()}`">{{ kind }}</span>
    <div class="file-card__info">
      <p class="file-card__name">{{ file.filename }}</p>
      <p class="file-card__meta">{{ size }}</p>
    </div>
    <button type="button" class="file-card__download" :disabled="downloading" @click="download">
      {{ downloading ? 'Descargando…' : 'Descargar' }}
    </button>
    <p v-if="error" class="file-card__error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.file-card {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-3) 0 0;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
}

.file-card__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  padding: 6px 8px;
  border-radius: var(--r-sm);
  background: var(--surface-subtle);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: var(--fw-semibold);
  letter-spacing: 0.04em;
}

.file-card__badge--excel {
  background: #e8f5ec;
  color: #1d6f42;
}

.file-card__badge--pdf {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.file-card__badge--word {
  background: #e8eef9;
  color: #2b579a;
}

.file-card__name {
  margin: 0;
  font-size: 13px;
  font-weight: var(--fw-medium);
  color: var(--text);
  overflow-wrap: anywhere;
}

.file-card__meta {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.file-card__download {
  padding: 6px var(--space-3);
  border: 1px solid var(--brand);
  border-radius: var(--r-sm);
  background: var(--brand);
  color: var(--text-on-brand, #fff);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  cursor: pointer;
}

.file-card__download:disabled {
  opacity: 0.7;
  cursor: progress;
}

.file-card__error {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 12.5px;
  color: var(--danger, #b42318);
}
</style>
