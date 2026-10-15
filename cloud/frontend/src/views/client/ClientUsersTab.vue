<script setup lang="ts">
import { Alert, Card, DataTable, EmptyState, type TableColumn, TextField } from '@savi/ui'
import { Users } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { formatInt, formatUsd, relativeTime } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const { id, client } = useClientContext()
const users = useAsync(() => consoleApi.clientUsers(id.value))
watch(id, () => users.reload())

// El ranking trae hasta 100 personas: se busca sobre lo ya cargado, por etiqueta o seudónimo.
const search = ref('')
const rows = computed(() => {
  const all = users.data.value ?? []
  const needle = search.value.trim().toLowerCase()
  if (!needle) return all
  return all.filter(
    (u) => u.user_ref.toLowerCase().includes(needle) || u.label?.toLowerCase().includes(needle),
  )
})

const COLUMNS: TableColumn[] = [
  { key: 'user_ref', label: 'Persona' },
  { key: 'turns', label: 'Turnos', align: 'right', width: '110px' },
  { key: 'cost_usd', label: 'Costo', align: 'right', width: '120px' },
  { key: 'databases_used', label: 'Sucursales', align: 'right', width: '110px' },
  { key: 'last_used_at', label: 'Último uso', width: '160px' },
]
</script>

<template>
  <div class="stack">
    <Alert v-if="client?.identity_mode !== 'named'" tone="info">
      Las personas se identifican por un seudónimo: Cloud no recibe nombres ni correos.
    </Alert>
    <TextField
      v-model="search"
      data-test="users-search"
      type="search"
      label="Buscar persona"
      placeholder="Código de usuario o seudónimo"
    />
    <Card padding="none">
      <DataTable
        :columns="COLUMNS"
        :rows="rows"
        row-key="user_ref"
        :loading="users.loading.value"
        caption="Personas que usaron SAVI"
      >
        <template #empty>
          <EmptyState
            :icon="Users"
            :title="search.trim() ? 'Ninguna persona coincide con la búsqueda' : 'Sin personas activas en el período'"
          />
        </template>
        <template #cell-user_ref="{ row }">
          <strong v-if="row.label">{{ row.label }}</strong>
          <code v-else>{{ row.user_ref.slice(0, 8) }}…</code>
        </template>
        <template #cell-turns="{ row }"><span class="num">{{ formatInt(row.turns) }}</span></template>
        <template #cell-cost_usd="{ row }">
          <span class="num">{{ formatUsd(row.cost_usd) }}</span>
        </template>
        <template #cell-last_used_at="{ row }">{{ relativeTime(row.last_used_at) }}</template>
      </DataTable>
    </Card>
    <p class="muted note">
      Ranking de los últimos 30 días: hasta 100 personas, ordenadas por turnos. Quien no usó SAVI
      en ese período no aparece acá, pero sí al configurar excepciones, reglas y grupos.
    </p>
  </div>
</template>

<style scoped>
.note {
  margin: 0;
  font-size: 12px;
}
</style>
