<script setup lang="ts">
/**
 * Turnos del chat que terminaron en error, con su código de soporte.
 *
 * Sirve para que el administrador del cliente le mande a soporte qué falló y
 * cuándo, sin tener que buscar el log en el equipo.
 */
import { onMounted, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import { formatFullDateTime } from '@/lib/dateTime'
import { HttpRequestError } from '@/lib/HttpClient'
import { type FailedTurn, failedTurnsService } from '../services/failedTurnsService'
import { failedTurnCategory } from '../utils/failedTurns'

const turns = ref<FailedTurn[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    turns.value = await failedTurnsService.list()
  } catch (error) {
    loadError.value =
      error instanceof HttpRequestError ? error.message : 'No se pudieron leer los turnos fallidos.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <header class="afail__header">
      <h1 class="afail__title">Turnos fallidos</h1>
      <p class="afail__subtitle">
        Respuestas del asistente que no se pudieron completar. Si una se repite, envíele a soporte
        el código de soporte: con él se encuentra la causa.
      </p>
    </header>

    <p v-if="loading" class="afail__muted">Cargando…</p>
    <p v-else-if="loadError" class="afail__error" role="alert">{{ loadError }}</p>
    <template v-else>
      <div class="afail__actions">
        <Button variant="secondary" @click="load">Actualizar</Button>
      </div>
      <p v-if="turns.length === 0" class="afail__muted" data-testid="failed-turns-empty">
        No hay turnos fallidos. Todas las respuestas se completaron.
      </p>
      <div v-else class="afail__table-wrap">
        <table class="afail__table" data-testid="failed-turns-table">
          <thead>
            <tr>
              <th scope="col">Fecha</th>
              <th scope="col">Conversación</th>
              <th scope="col">Causa</th>
              <th scope="col">Consultas al ERP</th>
              <th scope="col">Proveedor</th>
              <th scope="col">Código de soporte</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="turn in turns" :key="turn.message_id">
              <td>{{ formatFullDateTime(turn.created_at) }}</td>
              <td>{{ turn.conversation_title || 'Sin título' }}</td>
              <td>
                <span class="afail__category">{{ failedTurnCategory(turn.error_code) }}</span>
                <p v-if="turn.error_message" class="afail__detail">{{ turn.error_message }}</p>
              </td>
              <td>{{ turn.erp_queries }}</td>
              <td>{{ [turn.provider, turn.model].filter(Boolean).join(' · ') || '—' }}</td>
              <td>
                <code v-if="turn.support_code" class="afail__code">{{ turn.support_code }}</code>
                <span v-else>—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.afail__header {
  margin-bottom: var(--space-6);
}

.afail__title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display, var(--font-sans));
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  letter-spacing: 0.01em;
}

.afail__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 64ch;
  line-height: 1.5;
}

.afail__muted {
  margin: 0 0 var(--space-4);
  font-size: 13px;
  color: var(--text-muted);
}

.afail__error {
  margin: var(--space-3) 0;
  font-size: 13px;
  color: var(--danger, #b42318);
}

.afail__actions {
  margin-bottom: var(--space-4);
}

.afail__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.afail__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.afail__table th,
.afail__table td {
  padding: var(--space-3);
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}

.afail__table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
  background: var(--surface-subtle);
}

.afail__table tbody tr:last-child td {
  border-bottom: none;
}

.afail__category {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--r-sm);
  font-size: 12px;
  font-weight: var(--fw-medium);
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.afail__detail {
  margin: var(--space-1) 0 0;
  color: var(--text-muted);
  max-width: 48ch;
}

.afail__code {
  font-family: var(--font-mono, ui-monospace, monospace);
  letter-spacing: 0.04em;
  color: var(--text);
}
</style>
