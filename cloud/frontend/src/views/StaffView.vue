<script setup lang="ts">
import {
  Alert,
  Badge,
  Button,
  Card,
  DataTable,
  Dialog,
  EmptyState,
  PageHeader,
  Select,
  type TableColumn,
  TextField,
  toast,
  useZodForm,
} from '@savi/ui'
import { KeyRound, Plus, UserCheck, Users, UserX } from 'lucide-vue-next'
import { ref } from 'vue'
import { z } from 'zod'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import SecretDialog from '@/components/SecretDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime, roleLabel } from '@/lib/format'
import { ApiError } from '@/lib/http'
import type { Role, StaffMember } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const { data, loading, error, reload } = useAsync(() => consoleApi.staff())

const ROLES: { value: Role; label: string; description: string }[] = [
  // Espejo de la matriz `PERMISSIONS` de cloud/backend/app/modules/staff/domain.py.
  {
    value: 'admin',
    label: 'Administrador',
    description: 'Todo: políticas y suspensión de clientes, reglas de alerta y el equipo.',
  },
  {
    value: 'soporte',
    label: 'Soporte',
    description:
      'Instancias (detalle técnico y acciones), tokens de vinculación y alertas. No ve montos.',
  },
  {
    value: 'comercial',
    label: 'Comercial',
    description:
      'Alta y edición de clientes, suscripciones y pagos. Instancias y alertas solo lectura.',
  },
]
const ROLE_OPTIONS = ROLES.map(({ value, label }) => ({ value, label }))

const COLUMNS: TableColumn[] = [
  { key: 'full_name', label: 'Persona' },
  { key: 'role', label: 'Rol', width: '200px' },
  { key: 'status', label: 'Estado', width: '210px' },
  { key: 'last_login_at', label: 'Último ingreso', width: '170px' },
  { key: 'actions', label: '', align: 'right', width: '230px' },
]

// --- alta
const staffSchema = z.object({
  email: z.email('Ingresá un correo válido.'),
  full_name: z
    .string()
    .trim()
    .min(1, 'El nombre es obligatorio.')
    .max(200, 'El nombre admite hasta 200 caracteres.'),
  role: z.enum(['admin', 'soporte', 'comercial']),
})

const creating = ref(false)
const form = useZodForm(staffSchema, { email: '', full_name: '', role: 'soporte' })
const temporaryPassword = ref<string | null>(null)

function openCreate(): void {
  form.reset({ email: '', full_name: '', role: 'soporte' })
  creating.value = true
}

async function create(): Promise<void> {
  await form.handleSubmit(async (body) => {
    try {
      const created = await consoleApi.createStaff(body)
      creating.value = false
      temporaryPassword.value = created.temporary_password
      toast.success(`Usuario ${body.email} creado`)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'staff_email_already_exists') {
        form.setServerErrors({ email: e.message })
      } else {
        toast.error('No se pudo crear el usuario', { description: errorMessage(e) })
      }
    }
  })
}

async function closePassword(): Promise<void> {
  temporaryPassword.value = null
  await reload()
}

// --- cambio de rol (con confirmación: cambia lo que la persona puede ver y hacer)
const roleChange = ref<{ member: StaffMember; role: Role } | null>(null)
const roleBusy = ref(false)

async function applyRole(): Promise<void> {
  const change = roleChange.value
  if (!change) return
  roleBusy.value = true
  try {
    await consoleApi.updateStaff(change.member.id, { role: change.role })
    toast.success(`${change.member.full_name} ahora es ${roleLabel(change.role).toLowerCase()}`)
  } catch (e) {
    toast.error('No se pudo cambiar el rol', { description: errorMessage(e) })
  } finally {
    roleBusy.value = false
    roleChange.value = null
    await reload()
  }
}

// --- acciones
type Action = 'deactivate' | 'activate' | 'reset-mfa'
const pending = ref<{ member: StaffMember; action: Action } | null>(null)
const busy = ref(false)

const COPY: Record<
  Action,
  { title: string; message: string; confirm: string; danger: boolean; done: string }
> = {
  deactivate: {
    title: 'Desactivar usuario',
    message: 'Pierde el acceso de inmediato y se cierran sus sesiones.',
    confirm: 'Desactivar',
    danger: true,
    done: 'Usuario desactivado',
  },
  activate: {
    title: 'Reactivar usuario',
    message: 'Vuelve a poder ingresar con su contraseña y su TOTP.',
    confirm: 'Reactivar',
    danger: false,
    done: 'Usuario reactivado',
  },
  'reset-mfa': {
    title: 'Restablecer verificación en dos pasos',
    message:
      'Se cierran sus sesiones y en el próximo ingreso tendrá que configurar el TOTP de nuevo.',
    confirm: 'Restablecer',
    danger: true,
    done: 'Verificación restablecida',
  },
}

async function run(): Promise<void> {
  const current = pending.value
  if (!current) return
  busy.value = true
  try {
    await consoleApi.staffAction(current.member.id, current.action)
    toast.success(COPY[current.action].done)
  } catch (e) {
    toast.error('No se pudo completar la acción', { description: errorMessage(e) })
  } finally {
    busy.value = false
    pending.value = null
    await reload()
  }
}
</script>

<template>
  <div>
    <PageHeader title="Equipo" description="Personas de SEO Group con acceso a esta consola y su rol.">
      <template #actions>
        <Button data-test="staff-new" @click="openCreate">
          <Plus :size="15" aria-hidden="true" /> Nuevo usuario
        </Button>
      </template>
    </PageHeader>

    <div class="stack">
      <Alert v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </Alert>

      <Card padding="none">
        <DataTable :columns="COLUMNS" :rows="data ?? []" row-key="id" :loading="loading" caption="Equipo">
          <template #empty>
            <EmptyState :icon="Users" title="Todavía no hay usuarios" />
          </template>
          <template #cell-full_name="{ row }">
            <div class="person">
              <strong>{{ row.full_name }}</strong>
              <span>{{ row.email }}</span>
            </div>
          </template>
          <template #cell-role="{ row }">
            <Select
              v-if="row.id !== auth.user?.id"
              :model-value="row.role"
              :options="ROLE_OPTIONS"
              :aria-label="`Rol de ${row.full_name}`"
              @update:model-value="(role) => role && role !== row.role && (roleChange = { member: row, role })"
            />
            <span v-else>{{ roleLabel(row.role) }} <Badge tone="info">Vos</Badge></span>
          </template>
          <template #cell-status="{ row }">
            <div class="badges">
              <StatusBadge :tone="row.is_active ? 'ok' : 'muted'" :label="row.is_active ? 'Activo' : 'Inactivo'" />
              <StatusBadge :tone="row.mfa_enabled ? 'ok' : 'warn'" :label="row.mfa_enabled ? 'TOTP activo' : 'Sin TOTP'" />
            </div>
          </template>
          <template #cell-last_login_at="{ row }">{{ formatDateTime(row.last_login_at) }}</template>
          <template #cell-actions="{ row }">
            <div v-if="row.id !== auth.user?.id" class="actions">
              <Button
                v-if="row.is_active"
                variant="ghost"
                size="sm"
                @click="pending = { member: row, action: 'deactivate' }"
              >
                <UserX :size="14" aria-hidden="true" /> Desactivar
              </Button>
              <Button v-else variant="ghost" size="sm" @click="pending = { member: row, action: 'activate' }">
                <UserCheck :size="14" aria-hidden="true" /> Reactivar
              </Button>
              <Button variant="ghost" size="sm" @click="pending = { member: row, action: 'reset-mfa' }">
                <KeyRound :size="14" aria-hidden="true" /> Restablecer TOTP
              </Button>
            </div>
          </template>
        </DataTable>
      </Card>

      <Card title="Qué puede hacer cada rol" padding="md">
        <ul class="roles">
          <li v-for="role in ROLES" :key="role.value">
            <strong>{{ role.label }}</strong>
            <span>{{ role.description }}</span>
          </li>
        </ul>
      </Card>
    </div>

    <Dialog
      v-model:open="creating"
      title="Nuevo usuario"
      description="Se genera una contraseña temporal que se muestra una sola vez. En su primer ingreso la persona elige una nueva y configura el TOTP."
      :max-width="480"
    >
      <form id="staff-form" class="staff-form" novalidate @submit.prevent="create">
        <TextField
          v-model="form.values.email"
          label="Correo"
          type="email"
          required
          autocomplete="off"
          placeholder="nombre@seogroup.com"
          :error="form.errors.value.email"
          data-test="staff-email"
          @blur="form.touch('email')"
        />
        <TextField
          v-model="form.values.full_name"
          label="Nombre completo"
          required
          :maxlength="200"
          :error="form.errors.value.full_name"
          data-test="staff-name"
          @blur="form.touch('full_name')"
        />
        <Select
          v-model="form.values.role"
          label="Rol"
          :options="ROLE_OPTIONS"
          :hint="ROLES.find((r) => r.value === form.values.role)?.description"
          data-test="staff-role"
        />
      </form>
      <template #footer>
        <Button variant="ghost" :disabled="form.submitting.value" @click="creating = false">Cancelar</Button>
        <Button type="submit" form="staff-form" :loading="form.submitting.value" data-test="staff-save">
          Crear usuario
        </Button>
      </template>
    </Dialog>

    <ConfirmDialog
      :open="roleChange !== null"
      title="Cambiar el rol"
      :message="
        roleChange
          ? `${roleChange.member.full_name} pasa a ser ${roleLabel(roleChange.role).toLowerCase()}: cambia lo que puede ver y hacer desde su próximo pedido.`
          : ''
      "
      confirm-label="Cambiar rol"
      :danger="roleChange?.role === 'admin'"
      :busy="roleBusy"
      @confirm="applyRole"
      @cancel="roleChange = null"
    />

    <ConfirmDialog
      :open="pending !== null"
      :title="pending ? COPY[pending.action].title : ''"
      :message="pending ? `${pending.member.full_name}: ${COPY[pending.action].message}` : ''"
      :confirm-label="pending ? COPY[pending.action].confirm : 'Confirmar'"
      :danger="pending ? COPY[pending.action].danger : false"
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
.person {
  display: grid;
  gap: 2px;
}

.person span {
  font-size: 12px;
  color: var(--text-muted);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.actions {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-1);
}

.roles {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
}

.roles li {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: var(--space-3);
}

.roles span {
  color: var(--text-muted);
}

.staff-form {
  display: grid;
  gap: var(--space-5);
}
</style>
