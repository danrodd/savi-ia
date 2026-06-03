<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { renderMarkdown } from '@/lib/markdown'
import { parseSegments } from '@/lib/markdownSegments'

// Lazy: los motores de gráfica/diagrama solo se descargan cuando aparece un
// segmento que los usa. El chat sin gráficas no paga ese peso.
const SaviChart = defineAsyncComponent(() => import('./SaviChart.vue'))
const MermaidDiagram = defineAsyncComponent(() => import('./MermaidDiagram.vue'))

const props = defineProps<{ source: string }>()

const segments = computed(() => parseSegments(props.source))
</script>

<template>
  <div class="markdown">
    <template v-for="(seg, i) in segments" :key="`${seg.type}-${i}`">
      <!-- Prosa: markdown-it + DOMPurify, igual que antes. -->
      <div v-if="seg.type === 'prose'" v-html="renderMarkdown(seg.content)" />
      <SaviChart v-else-if="seg.type === 'chart'" :source="seg.content" />
      <MermaidDiagram v-else :source="seg.content" />
    </template>
  </div>
</template>

<style scoped>
.markdown {
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--text);
}

.markdown > *:first-child :deep(> *:first-child) {
  margin-top: 0;
}
.markdown > *:last-child :deep(> *:last-child) {
  margin-bottom: 0;
}

.markdown :deep(p) {
  margin: 0 0 12px;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  font-family: var(--font-display);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.01em;
  margin: 18px 0 8px;
  line-height: 1.3;
  color: var(--text);
}

.markdown :deep(h1) {
  font-size: 22px;
}
.markdown :deep(h2) {
  font-size: 18px;
}
.markdown :deep(h3) {
  font-size: 15.5px;
}
.markdown :deep(h4) {
  font-size: 14px;
  color: var(--text-muted);
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}

.markdown :deep(li) {
  margin: 4px 0;
}

.markdown :deep(li > p) {
  margin: 0;
}

.markdown :deep(a) {
  color: var(--brand);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
  transition: color var(--duration-fast) var(--ease-out);
}

.markdown :deep(a:hover) {
  color: var(--brand-strong);
}

.markdown :deep(code) {
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 5px;
  font-family: var(--font-mono);
  font-size: 0.875em;
  color: var(--text);
}

.markdown :deep(pre) {
  position: relative;
  background: var(--surface-sidebar);
  border: 1px solid var(--border);
  padding: var(--space-4) var(--space-5);
  border-radius: var(--r-md);
  overflow-x: auto;
  margin: 0 0 12px;
  box-shadow: var(--shadow-xs);
}

.markdown :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text);
}

.markdown :deep(blockquote) {
  margin: 0 0 12px;
  padding: var(--space-2) 0 var(--space-2) var(--space-4);
  border-left: 3px solid var(--brand);
  color: var(--text-muted);
  font-style: italic;
}

.markdown :deep(blockquote p) {
  margin: 0;
}

.markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 12px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  overflow: hidden;
}

.markdown :deep(th),
.markdown :deep(td) {
  border-bottom: 1px solid var(--border);
  padding: var(--space-3) var(--space-4);
  text-align: left;
}

.markdown :deep(tr:last-child td) {
  border-bottom: none;
}

.markdown :deep(th) {
  background: var(--surface-subtle);
  font-weight: var(--fw-semibold);
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.markdown :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 18px 0;
}

.markdown :deep(strong) {
  font-weight: var(--fw-semibold);
}
</style>
