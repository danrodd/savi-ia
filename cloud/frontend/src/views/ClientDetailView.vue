<script setup lang="ts">
import { Alert, Button, PageHeader, Skeleton, type TabItem, Tabs, toast } from '@savi/ui'
import { ArrowLeft, Pause, Pencil, Play } from 'lucide-vue-next'
import { computed, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import ClientFormDialog from '@/components/ClientFormDialog.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { CLIENT_CONTEXT } from '@/lib/clientContext'
import { relativeTime } from '@/lib/format'
import type { Permission } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const auth = useAuthStore()
const id = computed(() => String(route.params.id))

const client = useAsync(() => consoleApi.client(id.value))
// Contadores de las pestañas: una sola petición barata, aparte del detalle.
const counts = useAsync(() => consoleApi.clientCounts(id.value))
provide(CLIENT_CONTEXT, {
  id,
  client: client.data,
  reload: client.reload,
  counts: counts.data,
  reloadCounts: counts.reload,
})
// La vista se reutiliza al pasar de un cliente a otro: hay que recargar.
watch(id, () => {
  void client.reload()
  void counts.reload()
})

interface ClientTab {
  key: string
  label: string
  permission?: Permission
}

/** Mismo orden y permisos que las rutas hijas de `/clientes/:id` (router/index.ts). */
const TABS: ClientTab[] = [
  { key: 'resumen', label: 'Resumen' },
  { key: 'plan', label: 'Plan', permission: 'clients.billing' },
  { key: 'configuracion', label: 'Configuración', permission: 'clients.policy' },
  { key: 'operacion', label: 'Operación' },
  { key: 'vinculacion', label: 'Vinculación', permission: 'tokens.manage' },
  { key: 'alertas', label: 'Alertas' },
]

/** Cuántos hay en cada pestaña con contador; `undefined` (sin número) mientras no se sabe. */
function tabCount(key: string): number | undefined {
  if (key === 'operacion') return client.data.value?.instances_total
  if (key === 'alertas' && auth.can('alerts.read')) return counts.data.value?.open_alerts
  return undefined
}

const tabs = computed<TabItem[]>(() =>
  TABS.filter((tab) => !tab.permission || auth.can(tab.permission)).map((tab) => ({
    key: tab.key,
    label: tab.label,
    to: `/clientes/${id.value}/${tab.key}`,
    count: tabCount(tab.key),
  })),
)

const editing = ref(false)
const action = ref<'suspend' | 'activate' | null>(null)
const actionBusy = ref(false)

async function runClientAction(): Promise<void> {
  const current = action.value
  if (!current) return
  actionBusy.value = true
  try {
    if (current === 'suspend') await consoleApi.suspendClient(id.value)
    else await consoleApi.activateClient(id.value)
    toast.success(current === 'suspend' ? 'Cliente suspendido' : 'Cliente reactivado')
    await client.reload()
  } catch (e) {
    toast.error('No se pudo cambiar el estado del cliente', { description: errorMessage(e) })
  } finally {
    actionBusy.value = false
    action.value = null
  }
}
</script>

<template>
  <div>
    <RouterLink to="/clientes" class="back">
      <ArrowLeft :size="14" aria-hidden="true" /> Clientes
    </RouterLink>

    <Alert v-if="client.error.value" tone="danger">
      {{ client.error.value }}
      <template #action>
        <Button size="sm" variant="secondary" @click="client.reload()">Reintentar</Button>
      </template>
    </Alert>

    <div v-if="client.loading.value && !client.data.value" class="loading">
      <Skeleton height="30px" width="40%" />
      <Skeleton height="16px" width="25%" />
    </div>

    <template v-if="client.data.value">
      <PageHeader :title="client.data.value.name">
        <template #badges>
          <StatusBadge
            :tone="client.data.value.status === 'active' ? 'ok' : 'bad'"
            :label="client.data.value.status === 'active' ? 'Activo' : 'Suspendido'"
          />
        </template>
        <template #meta>
          <span><code>{{ client.data.value.code }}</code></span>
          <span v-if="client.data.value.nit">NIT {{ client.data.value.nit }}</span>
          <span>
            {{ client.data.value.instances_online }} de {{ client.data.value.instances_total }}
            instalaciones en línea
          </span>
          <span v-if="client.data.value.last_seen_at">
            Último contacto {{ relativeTime(client.data.value.last_seen_at) }}
          </span>
        </template>
        <template #actions>
          <Button
            v-if="auth.can('clients.write')"
            variant="secondary"
            data-test="client-edit"
            @click="editing = true"
          >
            <Pencil :size="14" aria-hidden="true" /> Editar
          </Button>
          <template v-if="auth.can('clients.suspend')">
            <Button
              v-if="client.data.value.status === 'active'"
              variant="secondary"
              data-test="client-suspend"
              @click="action = 'suspend'"
            >
              <Pause :size="14" aria-hidden="true" /> Suspender
            </Button>
            <Button v-else data-test="client-activate" @click="action = 'activate'">
              <Play :size="14" aria-hidden="true" /> Reactivar
            </Button>
          </template>
        </template>
      </PageHeader>

      <Alert v-if="client.data.value.status !== 'active'" tone="warning" class="suspended">
        Cliente suspendido: sus instalaciones no envían datos y no se pueden generar tokens nuevos.
      </Alert>

      <Tabs :items="tabs" label="Secciones del cliente" />

      <RouterView />
    </template>

    <ClientFormDialog
      v-model:open="editing"
      :client="client.data.value"
      @saved="client.reload()"
    />

    <ConfirmDialog
      :open="action !== null"
      :title="action === 'suspend' ? 'Suspender cliente' : 'Reactivar cliente'"
      :message="
        action === 'suspend'
          ? 'Se suspenden también todas sus instancias: dejan de enviar datos y no se pueden generar tokens nuevos.'
          : 'Se reactivan las instancias que se suspendieron junto con el cliente.'
      "
      :confirm-label="action === 'suspend' ? 'Suspender' : 'Reactivar'"
      :danger="action === 'suspend'"
      :busy="actionBusy"
      @confirm="runClientAction"
      @cancel="action = null"
    />
  </div>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 32px;
  margin-bottom: var(--space-4);
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}

.back:hover {
  color: var(--text);
  text-decoration: none;
}

.loading {
  display: grid;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.suspended {
  margin-bottom: var(--space-6);
}
</style>
