<script setup lang="ts">
import { ref } from 'vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { AuditEntry } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const entries = ref<AuditEntry[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const actor = ref('')
const action = ref('')
const expanded = ref<string | null>(null)

async function load(more = false): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const page = await consoleApi.audit({
      actor: actor.value || undefined,
      action: action.value || undefined,
      cursor: more ? (nextCursor.value ?? undefined) : undefined,
    })
    entries.value = more ? [...entries.value, ...page.items] : page.items
    nextCursor.value = page.next_cursor
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
void load()

function pretty(value: Record<string, unknown> | null): string {
  return value ? JSON.stringify(value, null, 2) : '—'
}
</script>

<template>
  <div class="stack">
    <h1>Auditoría</h1>
    <p class="muted">
      Registro de solo lectura de cada acción que modifica algo. Nunca contiene tokens ni
      contraseñas.
    </p>
    <form class="row" @submit.prevent="load()">
      <input v-model="actor" placeholder="Correo de quien actuó" type="email" class="filter" />
      <input v-model="action" placeholder="Acción (p. ej. instance.revoke)" class="filter" />
      <button class="btn" type="submit">Filtrar</button>
    </form>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Cuándo</th>
            <th>Quién</th>
            <th>Acción</th>
            <th>Objeto</th>
            <th>IP</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template v-for="e in entries" :key="e.id">
            <tr>
              <td>{{ formatDateTime(e.occurred_at) }}</td>
              <td>{{ e.actor_email ?? '—' }}</td>
              <td>
                <code>{{ e.action }}</code>
              </td>
              <td>
                <span v-if="e.target_type">{{ e.target_type }}</span>
                <span v-if="e.target_id" class="muted"> {{ e.target_id.slice(0, 8) }}…</span>
              </td>
              <td>{{ e.ip ?? '—' }}</td>
              <td>
                <button
                  v-if="e.before || e.after"
                  class="btn btn-small"
                  type="button"
                  @click="expanded = expanded === e.id ? null : e.id"
                >
                  {{ expanded === e.id ? 'Ocultar' : 'Ver cambio' }}
                </button>
              </td>
            </tr>
            <tr v-if="expanded === e.id">
              <td colspan="6">
                <div class="diff">
                  <div>
                    <strong>Antes</strong>
                    <pre>{{ pretty(e.before) }}</pre>
                  </div>
                  <div>
                    <strong>Después</strong>
                    <pre>{{ pretty(e.after) }}</pre>
                  </div>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="!loading && !entries.length">
            <td colspan="6" class="empty">No hay registros con esos filtros.</td>
          </tr>
        </tbody>
      </table>
    </div>
    <button v-if="nextCursor" class="btn" type="button" :disabled="loading" @click="load(true)">
      Ver más
    </button>
  </div>
</template>

<style scoped>
.filter {
  max-width: 280px;
}
.diff {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
}
pre {
  margin: 0.3rem 0 0;
  padding: 0.6rem;
  border-radius: 8px;
  background: var(--surface-subtle);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
