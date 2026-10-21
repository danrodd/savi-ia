<script setup lang="ts">
import { Button, ConfirmDialog } from '@savi/ui'
import { computed, onMounted, ref } from 'vue'
import { formatFullDateTime } from '@/lib/dateTime'
import { toast } from '@/lib/toast'
import CloudPreviewPanel from '../components/CloudPreviewPanel.vue'
import { useCloudLinkStore } from '../stores/cloudLinkStore'
import type { CloudHistoryMode } from '../types'
import {
  CLOUD_STATUS_HINTS,
  CLOUD_STATUS_LABELS,
  statusTone,
  streamLabel,
  streamProgress,
} from '../utils/cloudLink'

const store = useCloudLinkStore()

const token = ref('')
const history = ref<CloudHistoryMode>('all')
const linking = ref(false)
const syncing = ref(false)
const formError = ref<string | null>(null)
const unlinkOpen = ref(false)

const state = computed(() => store.state)
const linked = computed(() => store.isLinked)
const tone = computed(() => (state.value ? statusTone(state.value.status) : 'neutral'))
const canLink = computed(
  () => token.value.trim().length > 0 && !linking.value && state.value?.cloud_configured !== false,
)

function when(iso: string | null): string {
  return iso ? formatFullDateTime(iso) : 'Todavía no hubo contacto'
}

async function onLink(): Promise<void> {
  if (!canLink.value) return
  linking.value = true
  formError.value = null
  try {
    await store.link(token.value, history.value)
    token.value = ''
    toast.success('SAVI quedó vinculada con SAVI Cloud')
  } catch (e) {
    formError.value = (e as Error).message
  } finally {
    linking.value = false
  }
}

async function onSyncNow(): Promise<void> {
  syncing.value = true
  try {
    await store.syncNow()
    toast.success('Se pidió la sincronización. En unos instantes se actualiza el estado.')
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    syncing.value = false
  }
}

async function onUnlink(): Promise<void> {
  try {
    await store.unlink()
    toast.success('SAVI quedó desvinculada de SAVI Cloud')
  } catch (e) {
    toast.error((e as Error).message)
    throw e
  }
}

onMounted(() => void store.load())
</script>

<template>
  <section class="cl" data-testid="cloud-view">
    <header class="cl__header">
      <h1 class="cl__title">SAVI Cloud</h1>
      <p class="cl__subtitle">
        Conecte esta instalación con SAVI Cloud para que SEO Group pueda acompañarlo y darle soporte.
        Siempre puede ver qué datos se envían y desvincularla cuando quiera.
      </p>
    </header>

    <p v-if="store.error" class="cl__error" role="alert">
      {{ store.error }}
      <button type="button" class="cl__retry" @click="store.load()">Reintentar</button>
    </p>
    <p v-else-if="!state" class="cl__hint">Cargando…</p>

    <template v-else>
      <section v-if="!linked" class="cl__card" data-testid="cloud-unlinked">
        <h2 class="cl__h2">Vincular esta instalación</h2>
        <p v-if="!state.cloud_configured" class="cl__warn" role="status">
          Esta instalación todavía no tiene la dirección de SAVI Cloud configurada. Consulte con
          SEO Group.
        </p>
        <form class="cl__form" @submit.prevent="onLink">
          <label class="cl__field">
            <span>Token de vinculación</span>
            <input
              v-model="token"
              type="text"
              autocomplete="off"
              spellcheck="false"
              placeholder="svk_enr_…"
              :disabled="linking"
              data-testid="cloud-token"
            />
            <small>Se lo entrega SEO Group.</small>
          </label>

          <fieldset class="cl__field cl__radios">
            <legend>Historial</legend>
            <label>
              <input v-model="history" type="radio" value="all" />
              Enviar todo el historial
            </label>
            <label>
              <input v-model="history" type="radio" value="from_now" />
              Enviar solo desde hoy
            </label>
          </fieldset>

          <p v-if="formError" class="cl__error" role="alert" data-testid="cloud-form-error">
            {{ formError }}
          </p>

          <div>
            <Button type="submit" :disabled="!canLink" :loading="linking">Vincular</Button>
          </div>
        </form>
      </section>

      <section v-else class="cl__card" data-testid="cloud-linked">
        <div class="cl__row">
          <h2 class="cl__h2">{{ state.client_name || 'Instalación vinculada' }}</h2>
          <span
            class="cl__badge"
            :class="`cl__badge--${tone}`"
            data-testid="cloud-status"
          >{{ CLOUD_STATUS_LABELS[state.status] }}</span>
        </div>
        <p v-if="CLOUD_STATUS_HINTS[state.status]" class="cl__hint">
          {{ CLOUD_STATUS_HINTS[state.status] }}
        </p>

        <dl class="cl__facts">
          <div><dt>Último contacto</dt><dd>{{ when(state.last_heartbeat_ok_at) }}</dd></div>
          <div><dt>Vinculada desde</dt><dd>{{ when(state.linked_at) }}</dd></div>
        </dl>

        <h3 class="cl__h3">Envío de datos</h3>
        <ul v-if="state.streams.length" class="cl__streams" data-testid="cloud-streams">
          <li v-for="s in state.streams" :key="s.stream">
            <strong>{{ streamLabel(s.stream) }}:</strong> {{ streamProgress(s) }}
          </li>
        </ul>
        <p v-else class="cl__hint">Todavía no se envió ningún dato.</p>

        <div v-if="state.notices.length" class="cl__notices" data-testid="cloud-notices">
          <h3 class="cl__h3">Avisos de SAVI Cloud</h3>
          <ul>
            <li
              v-for="n in state.notices"
              :key="n.code"
              :class="`cl__notice cl__notice--${n.severity}`"
            >{{ n.message }}</li>
          </ul>
        </div>

        <div class="cl__actions">
          <Button variant="secondary" :loading="syncing" @click="onSyncNow">
            Sincronizar ahora
          </Button>
          <Button variant="danger" @click="unlinkOpen = true">Desvincular</Button>
        </div>
      </section>

      <CloudPreviewPanel
        :preview="store.preview"
        :loading="store.previewLoading"
        :error="store.previewError"
        @load="store.loadPreview()"
      />
    </template>

    <ConfirmDialog
      v-model:open="unlinkOpen"
      title="Desvincular de SAVI Cloud"
      description="SAVI dejará de enviar datos a SAVI Cloud. Para volver a conectarla va a necesitar un token nuevo de SEO Group."
      confirm-label="Desvincular"
      variant="danger"
      :on-confirm="onUnlink"
    />
  </section>
</template>

<style scoped>
.cl { display: grid; gap: var(--space-5); }
.cl__title { margin: 0 0 var(--space-2); font-family: var(--font-display, var(--font-sans)); font-size: 24px; font-weight: var(--fw-semibold); color: var(--text); }
.cl__subtitle { margin: 0; max-width: 62ch; font-size: 13px; line-height: 1.5; color: var(--text-muted); }
.cl__card { display: grid; gap: var(--space-3); padding: var(--space-5); border: 1px solid var(--border); border-radius: var(--r-md, 12px); background: var(--surface); }
.cl__h2 { margin: 0; font-size: 16px; font-weight: var(--fw-semibold); color: var(--text); }
.cl__h3 { margin: var(--space-2) 0 0; font-size: 13px; font-weight: var(--fw-semibold); color: var(--text); }
.cl__row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); }
.cl__hint { margin: 0; font-size: 13px; color: var(--text-muted); }
.cl__warn { margin: 0; padding: var(--space-2) var(--space-3); border-radius: var(--r-sm); background: var(--surface-subtle); color: var(--text-warning); font-size: 12px; }
.cl__form { display: grid; gap: var(--space-4); max-width: 480px; }
.cl__field { display: grid; gap: var(--space-1); font-size: 13px; color: var(--text); }
.cl__field input[type='text'] { padding: var(--space-2) var(--space-3); border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); color: var(--text); font: inherit; }
.cl__field small { color: var(--text-muted); }
.cl__radios { border: none; padding: 0; margin: 0; }
.cl__radios label { display: flex; align-items: center; gap: var(--space-2); }
.cl__badge { padding: 2px var(--space-3); border-radius: 999px; font-size: 12px; font-weight: var(--fw-semibold); }
.cl__badge--ok { background: var(--success-soft); color: var(--success); }
.cl__badge--warn { background: var(--surface-subtle); color: var(--warning); }
.cl__badge--danger { background: var(--surface-danger); color: var(--text-danger); }
.cl__badge--neutral { background: var(--surface-subtle); color: var(--text-muted); }
.cl__facts { display: flex; flex-wrap: wrap; gap: var(--space-6); margin: 0; font-size: 13px; }
.cl__facts dt { color: var(--text-subtle); font-size: 12px; }
.cl__facts dd { margin: 0; color: var(--text); }
.cl__streams, .cl__notices ul { margin: 0; padding-left: var(--space-5); font-size: 13px; line-height: 1.7; color: var(--text-muted); }
.cl__notice--critical { color: var(--text-danger); }
.cl__notice--warning { color: var(--warning); }
.cl__actions { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); }
.cl__error { display: flex; align-items: center; gap: var(--space-3); margin: 0; padding: var(--space-2) var(--space-3); border-radius: var(--r-sm); background: var(--surface-danger); color: var(--text-danger); font-size: 12px; }
.cl__retry { background: transparent; border: none; color: inherit; font: inherit; font-weight: var(--fw-semibold); text-decoration: underline; cursor: pointer; }
</style>
