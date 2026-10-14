<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()

const q = ref('')
const status = ref('')
const sort = ref('code')

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.clients({
    q: q.value || undefined,
    status: status.value || undefined,
    sort: sort.value,
  }),
)

let timer: ReturnType<typeof setTimeout> | undefined
watch([q, status, sort], () => {
  clearTimeout(timer)
  timer = setTimeout(() => void reload(), 250)
})

const creating = ref(false)
const form = ref({ code: '', name: '', nit: '' })
const formError = ref<string | null>(null)

async function create(): Promise<void> {
  formError.value = null
  try {
    await consoleApi.createClient({
      code: form.value.code.trim().toUpperCase(),
      name: form.value.name,
      nit: form.value.nit || null,
    })
    form.value = { code: '', name: '', nit: '' }
    creating.value = false
    await reload()
  } catch (e) {
    formError.value = errorMessage(e)
  }
}
</script>

<template>
  <div class="stack">
    <div class="spread">
      <h1>Clientes</h1>
      <button
        v-if="auth.can('clients.write')"
        class="btn btn-primary"
        type="button"
        @click="creating = !creating"
      >
        Nuevo cliente
      </button>
    </div>

    <form v-if="creating" class="card stack" @submit.prevent="create">
      <div class="fields">
        <label>
          Código (A-Z, 0-9, _)
          <input v-model="form.code" required minlength="2" maxlength="32" />
        </label>
        <label>
          Nombre
          <input v-model="form.name" required maxlength="200" />
        </label>
        <label>
          NIT (opcional)
          <input v-model="form.nit" maxlength="32" />
        </label>
      </div>
      <p v-if="formError" class="error-text" role="alert">{{ formError }}</p>
      <div class="row">
        <button class="btn btn-primary" type="submit">Crear cliente</button>
        <button class="btn" type="button" @click="creating = false">Cancelar</button>
      </div>
    </form>

    <div class="row">
      <input v-model="q" placeholder="Buscar por código o nombre" class="search" />
      <select v-model="status" class="select" aria-label="Estado">
        <option value="">Todos los estados</option>
        <option value="active">Activos</option>
        <option value="suspended">Suspendidos</option>
      </select>
      <select v-model="sort" class="select" aria-label="Orden">
        <option value="code">Ordenar por código</option>
        <option value="name">Ordenar por nombre</option>
        <option value="last_seen">Última actividad</option>
      </select>
    </div>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Código</th>
            <th>Nombre</th>
            <th>Estado</th>
            <th class="num">Instancias en línea</th>
            <th>Última actividad</th>
            <th>Versión más antigua</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in data?.items ?? []" :key="c.id">
            <td>
              <RouterLink :to="`/clientes/${c.id}`">
                <strong>{{ c.code }}</strong>
              </RouterLink>
            </td>
            <td>{{ c.name }}</td>
            <td>
              <StatusBadge
                :tone="c.status === 'active' ? 'ok' : 'bad'"
                :label="c.status === 'active' ? 'Activo' : 'Suspendido'"
              />
            </td>
            <td class="num">{{ c.instances_online }} / {{ c.instances_total }}</td>
            <td>{{ relativeTime(c.last_seen_at) }}</td>
            <td>{{ c.oldest_version ?? '—' }}</td>
          </tr>
          <tr v-if="!loading && !(data?.items.length ?? 0)">
            <td colspan="6" class="empty">No hay clientes con esos filtros.</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="data" class="muted">{{ data.total }} cliente(s).</p>
  </div>
</template>

<style scoped>
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.8rem;
}
.search {
  max-width: 320px;
}
.select {
  width: auto;
}
</style>
