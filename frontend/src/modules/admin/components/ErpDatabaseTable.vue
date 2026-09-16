<script setup lang="ts">
import type { ErpDatabase } from '../types'

defineProps<{
  databases: ErpDatabase[]
  busyId: string | null
}>()

const emit = defineEmits<{
  edit: [db: ErpDatabase]
  'set-default': [db: ErpDatabase]
  activate: [db: ErpDatabase]
  deactivate: [db: ErpDatabase]
  remove: [db: ErpDatabase]
}>()

const DEFAULT_LOCK_REASON = 'Designa otra base como predeterminada antes de desactivar o eliminar esta.'

const dateFormatter = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function formatDate(iso: string | null): string {
  return iso ? dateFormatter.format(new Date(iso)) : 'Nunca'
}

function statusOf(db: ErpDatabase): { label: string; tone: 'ok' | 'muted' | 'danger' } {
  if (db.credentials_unreadable) return { label: 'Credenciales ilegibles', tone: 'danger' }
  if (!db.is_active) return { label: 'Desactivada', tone: 'muted' }
  return { label: 'Activa', tone: 'ok' }
}
</script>

<template>
  <div class="dbtable__wrap">
    <table class="dbtable">
      <thead>
        <tr>
          <th scope="col">Cliente</th>
          <th scope="col">Conexión</th>
          <th scope="col">Estado</th>
          <th scope="col">Última conexión exitosa</th>
          <th scope="col"><span class="dbtable__sr">Acciones</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="db in databases" :key="db.id" :class="{ 'dbtable__row--inactive': !db.is_active }">
          <td data-label="Cliente">
            <div class="dbtable__name">
              {{ db.name }}
              <span v-if="db.is_default" class="dbtable__badge dbtable__badge--brand">Predeterminada</span>
            </div>
            <div class="dbtable__code">{{ db.code }}</div>
          </td>
          <td class="dbtable__mono" data-label="Conexión">
            {{ db.host }}:{{ db.port }}/{{ db.database }}
            <div class="dbtable__sub">{{ db.username }}</div>
          </td>
          <td data-label="Estado">
            <span class="dbtable__badge" :class="`dbtable__badge--${statusOf(db).tone}`">
              {{ statusOf(db).label }}
            </span>
            <div v-if="db.credentials_unreadable" class="dbtable__sub dbtable__sub--danger">
              Vuelve a ingresar la contraseña.
            </div>
          </td>
          <td class="dbtable__sub" data-label="Última conexión exitosa">
            {{ formatDate(db.last_connection_ok_at) }}
          </td>
          <td>
            <div class="dbtable__actions">
              <button type="button" class="dbtable__action" :disabled="busyId === db.id" @click="emit('edit', db)">
                Editar
              </button>
              <button
                v-if="!db.is_default && db.is_active"
                type="button"
                class="dbtable__action"
                :disabled="busyId === db.id || !db.is_usable"
                :title="db.is_usable ? undefined : 'Solo una base utilizable puede ser la predeterminada.'"
                @click="emit('set-default', db)"
              >
                Predeterminar
              </button>
              <button
                v-if="db.is_active"
                type="button"
                class="dbtable__action"
                :disabled="busyId === db.id || db.is_default"
                :title="db.is_default ? DEFAULT_LOCK_REASON : undefined"
                @click="emit('deactivate', db)"
              >
                Desactivar
              </button>
              <button
                v-else
                type="button"
                class="dbtable__action"
                :disabled="busyId === db.id"
                @click="emit('activate', db)"
              >
                Activar
              </button>
              <button
                type="button"
                class="dbtable__action dbtable__action--danger"
                :disabled="busyId === db.id || db.is_default"
                :title="db.is_default ? DEFAULT_LOCK_REASON : undefined"
                @click="emit('remove', db)"
              >
                Eliminar
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.dbtable__wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-elev);
}

.dbtable {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: var(--text);
}

.dbtable th {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.dbtable td {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.dbtable tbody tr:last-child td {
  border-bottom: none;
}

.dbtable__row--inactive td {
  color: var(--text-muted);
}

.dbtable__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-weight: var(--fw-medium);
}

.dbtable__code,
.dbtable__mono {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}

.dbtable__code {
  margin-top: 2px;
  color: var(--text-muted);
}

.dbtable__sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.dbtable__sub--danger {
  color: var(--text-danger, #b91c1c);
}

.dbtable__badge {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: 999px;
  font-size: 11px;
  font-weight: var(--fw-medium);
  white-space: nowrap;
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.dbtable__badge--brand {
  background: var(--brand);
  color: var(--text-on-brand);
}

.dbtable__badge--ok {
  background: var(--surface-success, rgba(22, 163, 74, 0.1));
  color: var(--text-success, #15803d);
}

.dbtable__badge--danger {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}

.dbtable__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-1);
}

.dbtable__action {
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: var(--fw-medium);
  cursor: pointer;
  white-space: nowrap;
}

.dbtable__action:hover:not(:disabled) {
  background: var(--surface-subtle);
  color: var(--text);
}

.dbtable__action--danger:hover:not(:disabled) {
  color: var(--text-danger, #b91c1c);
}

.dbtable__action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.dbtable__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

/* En pantallas angostas la tabla pasa a tarjetas.
   Con scroll horizontal, las acciones (Editar, Predeterminar, Desactivar,
   Eliminar) son la última columna y quedaban fuera de la pantalla sin ninguna
   señal de que estuvieran ahí: en un teléfono la fila se veía de solo lectura.
   Mismo patrón que la tabla de documentos. */
@media (max-width: 720px) {
  .dbtable__wrap {
    overflow-x: visible;
    border: none;
    background: transparent;
  }

  .dbtable,
  .dbtable tbody,
  .dbtable tr,
  .dbtable td {
    display: block;
    width: 100%;
  }

  .dbtable thead {
    display: none;
  }

  .dbtable tbody tr {
    margin-bottom: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    background: var(--surface-elev);
  }

  .dbtable td {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
  }

  /* Encabezado de la celda, tomado de `data-label`: sin la fila de títulos,
     una fecha o un host sueltos no dicen de qué son. */
  .dbtable td[data-label]::before {
    content: attr(data-label);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-subtle);
  }

  .dbtable tbody tr td:last-child {
    border-bottom: none;
  }

  .dbtable__actions {
    justify-content: flex-start;
    width: 100%;
  }

  .dbtable__action {
    border-color: var(--border);
    padding: var(--space-1) var(--space-3);
  }
}
</style>
