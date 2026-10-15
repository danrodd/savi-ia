<script setup lang="ts">
import { Button } from '@savi/ui'
import { computed } from 'vue'
import type { CloudPreview } from '../types'
import { EVENT_STREAM_HELP, HEARTBEAT_FIELD_HELP, NOT_SENT, streamLabel } from '../utils/cloudLink'

const props = defineProps<{
  preview: CloudPreview | null
  loading: boolean
  error: string | null
}>()
defineEmits<{ load: [] }>()

const heartbeatJson = computed(() => JSON.stringify(props.preview?.heartbeat ?? {}, null, 2))

const events = computed(() =>
  Object.entries(props.preview?.events ?? {}).map(([stream, payload]) => ({
    stream,
    label: streamLabel(stream),
    help: EVENT_STREAM_HELP[stream] ?? '',
    json: payload ? JSON.stringify(payload, null, 2) : null,
  })),
)
</script>

<template>
  <section class="cp" aria-labelledby="cloud-preview-title" data-testid="cloud-preview">
    <header class="cp__header">
      <div>
        <h2 id="cloud-preview-title" class="cp__title">Qué datos se envían</h2>
        <p class="cp__lead">
          Acá ves exactamente lo que viaja a SAVI Cloud, tal como se envía. Son datos de uso para
          que SEO Group pueda dar soporte y medir el piloto.
        </p>
      </div>
      <Button variant="secondary" size="sm" :loading="loading" @click="$emit('load')">
        {{ preview ? 'Actualizar' : 'Ver ejemplo' }}
      </Button>
    </header>

    <p v-if="error" class="cp__error" role="alert">{{ error }}</p>

    <div v-if="preview" class="cp__body">
      <h3 class="cp__h3">Estado de la instalación (cada pocos minutos)</h3>
      <pre class="cp__json" data-testid="cloud-preview-heartbeat">{{ heartbeatJson }}</pre>
      <dl class="cp__help">
        <template v-for="f in HEARTBEAT_FIELD_HELP" :key="f.key">
          <dt>{{ f.label }} <code>{{ f.key }}</code></dt>
          <dd>{{ f.help }}</dd>
        </template>
      </dl>

      <h3 class="cp__h3">Un ejemplo real de cada tipo de dato</h3>
      <article v-for="ev in events" :key="ev.stream" class="cp__event">
        <h4>{{ ev.label }}</h4>
        <p v-if="ev.help">{{ ev.help }}</p>
        <pre v-if="ev.json" class="cp__json">{{ ev.json }}</pre>
        <p v-else class="cp__empty">Por ahora no hay nada pendiente de enviar en este tipo.</p>
      </article>
    </div>

    <div class="cp__never">
      <h3 class="cp__h3">Lo que nunca se envía</h3>
      <ul data-testid="cloud-not-sent">
        <li v-for="item in NOT_SENT" :key="item">{{ item }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.cp {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--r-md, 12px);
  background: var(--surface);
}
.cp__header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-4); }
.cp__title { margin: 0 0 var(--space-1); font-size: 16px; font-weight: var(--fw-semibold); color: var(--text); }
.cp__lead { margin: 0; max-width: 62ch; font-size: 13px; line-height: 1.5; color: var(--text-muted); }
.cp__h3 { margin: var(--space-4) 0 var(--space-2); font-size: 13px; font-weight: var(--fw-semibold); color: var(--text); }
.cp__json {
  margin: 0;
  max-height: 280px;
  overflow: auto;
  padding: var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-subtle);
  font-size: 12px;
  line-height: 1.5;
}
.cp__help { display: grid; gap: var(--space-2); margin: var(--space-3) 0 0; font-size: 12px; }
.cp__help dt { font-weight: var(--fw-medium); color: var(--text); }
.cp__help dt code { margin-left: var(--space-1); color: var(--text-subtle); font-size: 11px; }
.cp__help dd { margin: 0; color: var(--text-muted); }
.cp__event h4 { margin: var(--space-3) 0 var(--space-1); font-size: 13px; }
.cp__event p { margin: 0 0 var(--space-2); font-size: 12px; color: var(--text-muted); }
.cp__empty { font-style: italic; }
.cp__never ul { margin: 0; padding-left: var(--space-5); font-size: 13px; color: var(--text-muted); line-height: 1.7; }
.cp__error { margin: 0; padding: var(--space-2) var(--space-3); border-radius: var(--r-sm); background: var(--surface-danger); color: var(--text-danger); font-size: 12px; }
</style>
