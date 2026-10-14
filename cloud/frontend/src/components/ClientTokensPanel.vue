<script setup lang="ts">
import { ref } from 'vue'
import SecretDialog from '@/components/SecretDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { EnrollmentToken } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; tokens: EnrollmentToken[]; loading: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const expiresHours = ref(72)
const createdToken = ref<string | null>(null)
const tokenError = ref<string | null>(null)

async function createToken(): Promise<void> {
  tokenError.value = null
  try {
    const created = await consoleApi.createToken(props.clientId, expiresHours.value)
    createdToken.value = created.token
  } catch (e) {
    tokenError.value = errorMessage(e)
  }
}

async function closeToken(): Promise<void> {
  // El token ya no se puede recuperar: se descarta de memoria al cerrar.
  createdToken.value = null
  emit('changed')
}

async function revokeToken(tokenId: string): Promise<void> {
  try {
    await consoleApi.revokeToken(tokenId)
    emit('changed')
  } catch (e) {
    tokenError.value = errorMessage(e)
  }
}

const TOKEN_STATE: Record<string, { label: string; tone: 'ok' | 'muted' | 'warn' | 'bad' }> = {
  pending: { label: 'Vigente', tone: 'ok' },
  used: { label: 'Usado', tone: 'muted' },
  expired: { label: 'Vencido', tone: 'warn' },
  revoked: { label: 'Revocado', tone: 'bad' },
}
</script>

<template>
<div class="stack">
  <div class="card row">
    <label class="hours">
      Vigencia del token (horas, hasta 168)
      <input v-model.number="expiresHours" type="number" min="1" max="168" />
    </label>
    <button class="btn btn-primary" type="button" @click="createToken">
      Generar token de vinculación
    </button>
  </div>
  <p v-if="tokenError" class="error-text" role="alert">{{ tokenError }}</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Estado</th>
          <th>Creado</th>
          <th>Vence</th>
          <th>Creado por</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in tokens" :key="t.id">
          <td>
            <StatusBadge
              :tone="TOKEN_STATE[t.state]?.tone ?? 'muted'"
              :label="TOKEN_STATE[t.state]?.label ?? t.state"
            />
          </td>
          <td>{{ formatDateTime(t.created_at) }}</td>
          <td>{{ formatDateTime(t.expires_at) }}</td>
          <td>{{ t.created_by }}</td>
          <td>
            <button
              v-if="t.state === 'pending'"
              class="btn btn-small btn-danger"
              type="button"
              @click="revokeToken(t.id)"
            >
              Revocar
            </button>
          </td>
        </tr>
        <tr v-if="!loading && tokens.length === 0">
          <td colspan="5" class="empty">Todavía no se generó ningún token.</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>

<SecretDialog
  :open="createdToken !== null"
  title="Token de vinculación"
  :secret="createdToken ?? ''"
  instructions="Pegalo en SAVI → Administración → SAVI Cloud, o en el instalador."
  @close="closeToken"
/>
</template>

<style scoped>
.hours {
  max-width: 280px;
}
</style>
