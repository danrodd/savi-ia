<script setup lang="ts">
import { ref } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SecretDialog from '@/components/SecretDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime, roleLabel } from '@/lib/format'
import type { Role, StaffMember } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const { data, loading, error, reload } = useAsync(() => consoleApi.staff())

const creating = ref(false)
const form = ref<{ email: string; full_name: string; role: Role }>({
  email: '',
  full_name: '',
  role: 'soporte',
})
const actionError = ref<string | null>(null)
const temporaryPassword = ref<string | null>(null)

async function create(): Promise<void> {
  actionError.value = null
  try {
    const created = await consoleApi.createStaff(form.value)
    temporaryPassword.value = created.temporary_password
    form.value = { email: '', full_name: '', role: 'soporte' }
    creating.value = false
    await reload()
  } catch (e) {
    actionError.value = errorMessage(e)
  }
}

async function closePassword(): Promise<void> {
  temporaryPassword.value = null
  await reload()
}

async function changeRole(member: StaffMember, role: Role): Promise<void> {
  actionError.value = null
  try {
    await consoleApi.updateStaff(member.id, { role })
  } catch (e) {
    actionError.value = errorMessage(e)
  } finally {
    await reload()
  }
}

type Action = 'deactivate' | 'activate' | 'reset-mfa'
const pending = ref<{ member: StaffMember; action: Action } | null>(null)
const busy = ref(false)

const COPY: Record<Action, { title: string; message: string; confirm: string; danger: boolean }> = {
  deactivate: {
    title: 'Desactivar usuario',
    message: 'Pierde el acceso de inmediato y se cierran sus sesiones.',
    confirm: 'Desactivar',
    danger: true,
  },
  activate: {
    title: 'Reactivar usuario',
    message: 'Vuelve a poder ingresar con su contraseña y su TOTP.',
    confirm: 'Reactivar',
    danger: false,
  },
  'reset-mfa': {
    title: 'Restablecer verificación en dos pasos',
    message:
      'Se cierran sus sesiones y en el próximo ingreso tendrá que configurar el TOTP de nuevo.',
    confirm: 'Restablecer',
    danger: true,
  },
}

async function run(): Promise<void> {
  if (!pending.value) return
  busy.value = true
  actionError.value = null
  try {
    await consoleApi.staffAction(pending.value.member.id, pending.value.action)
  } catch (e) {
    actionError.value = errorMessage(e)
  } finally {
    busy.value = false
    pending.value = null
    await reload()
  }
}
</script>

<template>
  <div class="stack">
    <div class="spread">
      <h1>Equipo</h1>
      <button class="btn btn-primary" type="button" @click="creating = !creating">
        Nuevo usuario
      </button>
    </div>

    <form v-if="creating" class="card stack" @submit.prevent="create">
      <div class="fields">
        <label>
          Correo
          <input v-model="form.email" type="email" required />
        </label>
        <label>
          Nombre completo
          <input v-model="form.full_name" required maxlength="200" />
        </label>
        <label>
          Rol
          <select v-model="form.role">
            <option value="admin">Administrador</option>
            <option value="soporte">Soporte</option>
            <option value="comercial">Comercial</option>
          </select>
        </label>
      </div>
      <p class="muted">
        Se genera una contraseña temporal que se muestra una sola vez. En su primer ingreso la
        persona elige una nueva y configura el TOTP.
      </p>
      <div class="row">
        <button class="btn btn-primary" type="submit">Crear usuario</button>
        <button class="btn" type="button" @click="creating = false">Cancelar</button>
      </div>
    </form>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="actionError" class="error-text" role="alert">{{ actionError }}</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Persona</th>
            <th>Rol</th>
            <th>Estado</th>
            <th>Último ingreso</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in data ?? []" :key="m.id">
            <td>
              <strong>{{ m.full_name }}</strong>
              <div class="muted">{{ m.email }}</div>
            </td>
            <td>
              <select
                v-if="m.id !== auth.user?.id"
                :value="m.role"
                class="select"
                :aria-label="`Rol de ${m.full_name}`"
                @change="changeRole(m, ($event.target as HTMLSelectElement).value as Role)"
              >
                <option value="admin">Administrador</option>
                <option value="soporte">Soporte</option>
                <option value="comercial">Comercial</option>
              </select>
              <span v-else>{{ roleLabel(m.role) }} (vos)</span>
            </td>
            <td>
              <StatusBadge
                :tone="m.is_active ? 'ok' : 'muted'"
                :label="m.is_active ? 'Activo' : 'Inactivo'"
              />
              <StatusBadge
                :tone="m.mfa_enabled ? 'ok' : 'warn'"
                :label="m.mfa_enabled ? 'TOTP activo' : 'Sin TOTP'"
              />
            </td>
            <td>{{ formatDateTime(m.last_login_at) }}</td>
            <td>
              <div v-if="m.id !== auth.user?.id" class="row">
                <button
                  v-if="m.is_active"
                  class="btn btn-small btn-danger"
                  type="button"
                  @click="pending = { member: m, action: 'deactivate' }"
                >
                  Desactivar
                </button>
                <button
                  v-else
                  class="btn btn-small"
                  type="button"
                  @click="pending = { member: m, action: 'activate' }"
                >
                  Reactivar
                </button>
                <button
                  class="btn btn-small"
                  type="button"
                  @click="pending = { member: m, action: 'reset-mfa' }"
                >
                  Restablecer TOTP
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && !(data?.length ?? 0)">
            <td colspan="5" class="empty">Todavía no hay usuarios.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <ConfirmDialog
      v-if="pending"
      :open="true"
      :title="COPY[pending.action].title"
      :message="`${pending.member.full_name}: ${COPY[pending.action].message}`"
      :confirm-label="COPY[pending.action].confirm"
      :danger="COPY[pending.action].danger"
      :busy="busy"
      @confirm="run"
      @cancel="pending = null"
    />
    <SecretDialog
      :open="temporaryPassword !== null"
      title="Contraseña temporal"
      :secret="temporaryPassword ?? ''"
      instructions="Pasásela a la persona por un canal seguro. Tendrá que cambiarla en su primer ingreso."
      @close="closePassword"
    />
  </div>
</template>

<style scoped>
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.8rem;
}
.select {
  width: auto;
}
</style>
