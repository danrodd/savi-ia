<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { triggerDownload } from '@/lib/download'
import DownloadButton from './DownloadButton.vue'

const props = defineProps<{ source: string }>()

const host = ref<HTMLElement | null>(null)
const failed = ref(false)

function download(): void {
  const svg = host.value?.querySelector('svg')
  if (!svg) return
  const xml = new XMLSerializer().serializeToString(svg)
  const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  triggerDownload(url, 'diagrama.svg')
  // Revocamos en el próximo tick para no cancelar la descarga en curso.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

// Contador de módulo para IDs únicos de render (mermaid lo exige) sin recurrir
// a Math.random.
let seq = 0

async function render(): Promise<void> {
  const code = props.source.trim()
  if (!code) return
  try {
    // Lazy: mermaid solo entra al bundle cuando aparece un diagrama.
    const mermaid = (await import('mermaid')).default
    mermaid.initialize({
      startOnLoad: false,
      // 'strict' sanitiza el SVG y bloquea HTML/JS arbitrario — clave en un ERP.
      securityLevel: 'strict',
      theme: 'neutral',
      fontFamily: 'inherit',
    })
    seq += 1
    const { svg } = await mermaid.render(`savi-mermaid-${seq}`, code)
    if (host.value) host.value.innerHTML = svg
    failed.value = false
  } catch {
    failed.value = true
  }
}

onMounted(render)
watch(() => props.source, render)
</script>

<template>
  <div v-show="!failed" class="mermaid-diagram">
    <Tooltip text="Descargar SVG" side="right">
      <DownloadButton class="mermaid-diagram__download" label="Descargar SVG" @click="download" />
    </Tooltip>
    <div ref="host" class="mermaid-diagram__svg" aria-label="Diagrama" />
  </div>
  <!-- Degradación elegante: si mermaid falla, mostramos el código del diagrama. -->
  <pre v-if="failed" class="mermaid-diagram__fallback"><code>{{ source }}</code></pre>
</template>

<style scoped>
.mermaid-diagram {
  position: relative;
  margin: 0 0 12px;
  padding: var(--space-4);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow-x: auto;
  text-align: center;
}

.mermaid-diagram__download {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  z-index: 1;
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.mermaid-diagram:hover .mermaid-diagram__download,
.mermaid-diagram:focus-within .mermaid-diagram__download {
  opacity: 1;
}

@media (hover: none) {
  .mermaid-diagram__download {
    opacity: 1;
  }
}

.mermaid-diagram :deep(svg) {
  max-width: 100%;
  height: auto;
}

.mermaid-diagram__fallback {
  margin: 0 0 12px;
  padding: var(--space-4) var(--space-5);
  background: var(--surface-sidebar);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
