<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { instanceStatusLabel, relativeTime } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const status = ref('')
const connectivity = ref('')
const outdated = ref(false)

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.instances({
    status: status.value || undefined,
    connectivity: connectivity.value || undefined,
    outdated: outdated.value || undefined,
  }),
)

watch([status, connectivity, outdated], () => void reload())
</script>

<template>
  <div class="stack">
    <h1>Instancias</h1>
    <div class="row">
      <select v-model="status" class="select" aria-label="Estado">
        <option value="">Todos los estados</option>
        <option value="active">Activas</option>
        <option value="suspended">Suspendidas</option>
        <option value="revoked">Revocadas</option>
      </select>
      <select v-model="connectivity" class="select" aria-label="Conexión">
        <option value="">Con o sin conexión</option>
        <option value="online">En línea</option>
        <option value="offline">Sin conexión</option>
      </select>
      <label class="check">
        <input v-model="outdated" type="checkbox" />
        Solo desactualizadas
      </label>
    </div>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Instancia</th>
            <th>Cliente</th>
            <th>Estado</th>
            <th>Versión</th>
            <th>Último contacto</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="i in data ?? []" :key="i.id">
            <td>
              <RouterLink :to="`/instancias/${i.id}`">{{ i.name }}</RouterLink>
            </td>
            <td>
              <RouterLink :to="`/clientes/${i.client_id}`">{{ i.client_code }}</RouterLink>
            </td>
            <td>
              <StatusBadge
                :tone="i.status === 'active' ? (i.online ? 'ok' : 'warn') : 'bad'"
                :label="
                  i.status === 'active'
                    ? i.online
                      ? 'En línea'
                      : 'Sin conexión'
                    : instanceStatusLabel(i.status)
                "
              />
            </td>
            <td>
              {{ i.version ?? '—' }}
              <StatusBadge v-if="i.outdated" tone="warn" label="Desactualizada" />
            </td>
            <td>{{ relativeTime(i.last_seen_at) }}</td>
          </tr>
          <tr v-if="!loading && !(data?.length ?? 0)">
            <td colspan="5" class="empty">No hay instancias con esos filtros.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.select {
  width: auto;
}
.check {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--text);
}
.check input {
  width: auto;
}
</style>
