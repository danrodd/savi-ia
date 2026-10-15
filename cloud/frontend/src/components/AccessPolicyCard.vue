<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { consoleApi } from '@/lib/api'
import type { AccessGroup, AccessPolicy, ClientDatabase, ClientUser } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; policy: AccessPolicy }>()
const emit = defineEmits<{ saved: [] }>()

const databases = ref<ClientDatabase[]>([])
const people = ref<ClientUser[]>([])

// `null` = sin restricción general (manda lo que permita el ERP).
const limitDefault = ref(false)
const defaultDbs = ref<string[]>([])
const rules = ref<{ user_ref: string; databases: string[] }[]>([])
const groups = ref<AccessGroup[]>([])
const newGroupName = ref('')

const newRef = ref('')
const confirming = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)

function hydrate(policy: AccessPolicy): void {
  limitDefault.value = policy.default_databases !== null
  defaultDbs.value = [...(policy.default_databases ?? [])]
  rules.value = Object.entries(policy.user_databases).map(([user_ref, dbs]) => ({
    user_ref,
    databases: [...dbs],
  }))
  groups.value = policy.groups.map((g) => ({
    id: g.id,
    name: g.name,
    members: [...g.members],
    databases: [...g.databases],
    user_monthly_usd: g.user_monthly_usd,
  }))
}

watch(() => props.policy, hydrate, { immediate: true })

onMounted(async () => {
  const [dbs, users] = await Promise.allSettled([
    consoleApi.clientDatabases(props.clientId),
    consoleApi.clientUsers(props.clientId),
  ])
  databases.value = dbs.status === 'fulfilled' ? dbs.value : []
  people.value = users.status === 'fulfilled' ? users.value : []
})

function personLabel(ref: string): string {
  return people.value.find((p) => p.user_ref === ref)?.label ?? `${ref.slice(0, 8)}…`
}

const candidates = computed(() =>
  people.value.filter((p) => !rules.value.some((r) => r.user_ref === p.user_ref)),
)

function addRule(): void {
  if (!newRef.value) return
  rules.value.push({ user_ref: newRef.value, databases: [] })
  newRef.value = ''
}

function addGroup(): void {
  const name = newGroupName.value.trim()
  if (!name) return
  if (groups.value.some((g) => g.name.toLowerCase() === name.toLowerCase())) {
    error.value = 'Ya hay un grupo con ese nombre.'
    return
  }
  error.value = null
  groups.value.push({ id: null, name, members: [], databases: [], user_monthly_usd: null })
  newGroupName.value = ''
}

function removeGroup(index: number): void {
  groups.value.splice(index, 1)
}

function removeRule(ref: string): void {
  rules.value = rules.value.filter((r) => r.user_ref !== ref)
}

function toggle(list: string[], ref: string): string[] {
  return list.includes(ref) ? list.filter((r) => r !== ref) : [...list, ref]
}

function buildBody(): AccessPolicy {
  return {
    default_databases: limitDefault.value ? [...defaultDbs.value] : null,
    user_databases: Object.fromEntries(rules.value.map((r) => [r.user_ref, [...r.databases]])),
    groups: groups.value.map((g) => ({
      id: g.id,
      name: g.name,
      members: [...g.members],
      databases: [...g.databases],
      user_monthly_usd: g.user_monthly_usd?.trim() ? g.user_monthly_usd.trim() : null,
    })),
  }
}

const hasEmptyRule = computed(() => rules.value.some((r) => r.databases.length === 0))
const defaultIsEmpty = computed(() => limitDefault.value && defaultDbs.value.length === 0)

async function save(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await consoleApi.setClientAccessPolicy(props.clientId, buildBody())
    emit('saved')
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
    confirming.value = false
  }
}
</script>

<template>
  <section class="card access" data-test="access-policy">
    <h2>Bases por persona</h2>
    <p class="muted">
      Restringe qué bases de clientes puede consultar cada persona. Solo acota: la persona además
      tiene que tener acceso en el ERP. Sin restricción, manda lo que permita el ERP. Aplica en el
      próximo contacto de cada instalación.
    </p>
    <p v-if="error" class="error-text" role="alert" data-test="access-error">{{ error }}</p>

    <label class="check">
      <input v-model="limitDefault" type="checkbox" data-test="access-limit-default" />
      Limitar las bases de todas las personas sin regla propia
    </label>

    <fieldset v-if="limitDefault">
      <legend>Bases permitidas por defecto</legend>
      <label v-for="d in databases" :key="d.database_ref" class="check">
        <input
          type="checkbox"
          :checked="defaultDbs.includes(d.database_ref)"
          :data-test="`access-default-${d.database_ref}`"
          @change="defaultDbs = toggle(defaultDbs, d.database_ref)"
        />
        {{ d.name }} <span class="muted">({{ d.code }})</span>
      </label>
      <p v-if="!databases.length" class="muted">Todavía no hay bases reportadas por este cliente.</p>
      <p v-if="defaultIsEmpty" class="warn-text" data-test="access-default-empty">
        Sin ninguna base marcada, nadie sin regla propia podrá consultar.
      </p>
    </fieldset>

    <fieldset>
      <legend>Grupos</legend>
      <p class="muted">
        Un grupo reúne personas que comparten las mismas bases y, si querés, un tope mensual de IA.
        Quien está en varios grupos recibe la unión de sus bases y el mayor de sus topes; una regla
        propia de la persona manda sobre los grupos.
      </p>
      <div v-for="(g, index) in groups" :key="g.id ?? g.name" class="rule" data-test="access-group">
        <div class="rule__head">
          <strong>{{ g.name }}</strong>
          <button class="btn btn-small" type="button" @click="removeGroup(index)">Quitar</button>
        </div>
        <details>
          <summary>Personas ({{ g.members.length }})</summary>
          <label v-for="p in people" :key="p.user_ref" class="check">
            <input
              type="checkbox"
              :checked="g.members.includes(p.user_ref)"
              :data-test="`access-group-${g.name}-person-${p.user_ref}`"
              @change="g.members = toggle(g.members, p.user_ref)"
            />
            {{ p.label ?? `${p.user_ref.slice(0, 8)}…` }}
          </label>
          <p v-if="!people.length" class="muted">Todavía no hay personas con consumo registrado.</p>
        </details>
        <label class="cap">
          Tope mensual de IA por persona (USD)
          <input
            v-model="g.user_monthly_usd"
            inputmode="decimal"
            placeholder="Sin tope"
            :data-test="`access-group-${g.name}-cap`"
          />
        </label>
        <details open>
          <summary>Bases ({{ g.databases.length }})</summary>
          <label v-for="d in databases" :key="d.database_ref" class="check">
            <input
              type="checkbox"
              :checked="g.databases.includes(d.database_ref)"
              :data-test="`access-group-${g.name}-db-${d.database_ref}`"
              @change="g.databases = toggle(g.databases, d.database_ref)"
            />
            {{ d.name }} <span class="muted">({{ d.code }})</span>
          </label>
        </details>
      </div>
      <div class="row">
        <input
          v-model="newGroupName"
          placeholder="Nombre del grupo"
          aria-label="Nombre del grupo"
          data-test="access-group-name"
          @keydown.enter.prevent="addGroup"
        />
        <button class="btn btn-small" type="button" data-test="access-group-add" @click="addGroup">
          Agregar grupo
        </button>
      </div>
    </fieldset>

    <fieldset>
      <legend>Reglas por persona</legend>
      <p class="muted">Reemplazan la regla general. Sin ninguna base marcada, la persona no consulta.</p>
      <div v-for="r in rules" :key="r.user_ref" class="rule" data-test="access-rule">
        <div class="rule__head">
          <strong>{{ personLabel(r.user_ref) }}</strong>
          <button class="btn btn-small" type="button" @click="removeRule(r.user_ref)">Quitar</button>
        </div>
        <label v-for="d in databases" :key="d.database_ref" class="check">
          <input
            type="checkbox"
            :checked="r.databases.includes(d.database_ref)"
            :data-test="`access-rule-${r.user_ref}-${d.database_ref}`"
            @change="r.databases = toggle(r.databases, d.database_ref)"
          />
          {{ d.name }} <span class="muted">({{ d.code }})</span>
        </label>
      </div>
      <div class="row">
        <select v-model="newRef" data-test="access-rule-person" aria-label="Persona">
          <option value="">Elegí una persona</option>
          <option v-for="p in candidates" :key="p.user_ref" :value="p.user_ref">
            {{ p.label ?? `${p.user_ref.slice(0, 8)}…` }}
          </option>
        </select>
        <button class="btn btn-small" type="button" data-test="access-rule-add" @click="addRule">
          Agregar regla
        </button>
      </div>
      <p v-if="hasEmptyRule" class="warn-text" data-test="access-rule-empty">
        Hay reglas sin ninguna base: esas personas no podrán consultar.
      </p>
    </fieldset>

    <div class="row actions">
      <button
        class="btn btn-primary"
        type="button"
        data-test="access-save"
        @click="confirming = true"
      >
        Guardar
      </button>
    </div>

    <ConfirmDialog
      :open="confirming"
      title="Guardar las bases por persona"
      message="Las instalaciones de este cliente aplicarán estas reglas en su próximo contacto. Quien no tenga la base asignada no podrá consultarla desde SAVI."
      confirm-label="Guardar reglas"
      :busy="busy"
      @confirm="save"
      @cancel="confirming = false"
    />
  </section>
</template>

<style scoped>
.access {
  display: grid;
  gap: 0.9rem;
}
.access fieldset {
  display: grid;
  gap: 0.5rem;
  border: 1px solid var(--border, #d0d5dd);
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
  min-width: 0;
}
.check {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}
.rule {
  display: grid;
  gap: 0.35rem;
  padding: 0.5rem 0;
  border-top: 1px solid var(--border, #e4e7ec);
}
.cap {
  max-width: 280px;
}
.rule__head {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: center;
  justify-content: space-between;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.warn-text {
  margin: 0;
  color: var(--warning, #b54708);
}
</style>
