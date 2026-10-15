<script setup lang="ts">
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Select,
  Switch,
  TextField,
  toast,
  UnsavedBar,
  useZodForm,
} from '@savi/ui'
import { Trash2, UserRound, UsersRound } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { consoleApi } from '@/lib/api'
import { accessPolicySchema, toBody, toForm } from '@/lib/schemas/accessPolicy'
import type { AccessPolicy, ClientDatabase, ClientUser } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; policy: AccessPolicy }>()
const emit = defineEmits<{ saved: [] }>()

const form = useZodForm(accessPolicySchema, toForm(props.policy))
watch(
  () => props.policy,
  (policy) => form.reset(toForm(policy)),
)

const databases = ref<ClientDatabase[]>([])
const people = ref<ClientUser[]>([])

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

function toggle(list: string[], ref: string, on: boolean): string[] {
  return on ? [...new Set([...list, ref])] : list.filter((r) => r !== ref)
}

// Alta de grupos y reglas: se validan acá, aparte del formulario principal.
const newGroupName = ref('')
const groupError = ref<string | null>(null)
const newRef = ref<string | null>(null)

const candidates = computed(() =>
  people.value
    .filter((p) => !form.values.rules.some((r) => r.user_ref === p.user_ref))
    .map((p) => ({ value: p.user_ref, label: p.label ?? `${p.user_ref.slice(0, 8)}…` })),
)

function addGroup(): void {
  const name = newGroupName.value.trim()
  groupError.value = null
  if (!name) {
    groupError.value = 'Escribí un nombre para el grupo.'
    return
  }
  if (form.values.groups.some((g) => g.name.toLowerCase() === name.toLowerCase())) {
    groupError.value = 'Ya hay un grupo con ese nombre.'
    return
  }
  form.values.groups.push({ id: null, name, members: [], databases: [], cap: '' })
  newGroupName.value = ''
}

function addRule(): void {
  if (!newRef.value) return
  form.values.rules.push({ user_ref: newRef.value, databases: [] })
  newRef.value = null
}

const hasEmptyRule = computed(() => form.values.rules.some((r) => r.databases.length === 0))
const defaultIsEmpty = computed(
  () => form.values.limitDefault && form.values.defaultDbs.length === 0,
)

const confirming = ref(false)
const busy = ref(false)

function askToSave(): void {
  void form.handleSubmit(() => {
    confirming.value = true
  })
}

async function save(): Promise<void> {
  const parsed = accessPolicySchema.safeParse(form.values)
  if (!parsed.success) {
    confirming.value = false
    return
  }
  busy.value = true
  try {
    await consoleApi.setClientAccessPolicy(props.clientId, toBody(parsed.data))
    toast.success('Reglas de acceso guardadas', {
      description: 'Las instalaciones las aplican en su próximo contacto.',
    })
    emit('saved')
  } catch (e) {
    toast.error('No se pudieron guardar las reglas', { description: errorMessage(e) })
  } finally {
    busy.value = false
    confirming.value = false
  }
}
</script>

<template>
  <div class="access" data-test="access-policy">
    <Alert tone="info">
      Estas reglas solo acotan: la persona además tiene que tener acceso en el ERP. Una regla propia
      manda sobre los grupos, y los grupos sobre la regla general.
    </Alert>

    <Card title="Regla general" description="Para todas las personas que no tienen grupo ni regla propia.">
      <Switch
        v-model="form.values.limitDefault"
        label="Limitar las bases por defecto"
        :description="
          form.values.limitDefault
            ? 'Solo pueden consultar las bases marcadas.'
            : 'Sin límite: cada persona consulta lo que le permita el ERP.'
        "
        data-test="access-limit-default"
      />
      <div v-if="form.values.limitDefault" class="access__dbs">
        <Checkbox
          v-for="d in databases"
          :key="d.database_ref"
          :model-value="form.values.defaultDbs.includes(d.database_ref)"
          :label="d.name"
          :description="d.code"
          :data-test="`access-default-${d.database_ref}`"
          @update:model-value="form.values.defaultDbs = toggle(form.values.defaultDbs, d.database_ref, $event)"
        />
        <p v-if="!databases.length" class="muted">Todavía no hay bases reportadas por este cliente.</p>
      </div>
      <Alert v-if="defaultIsEmpty" tone="warning" class="access__alert" data-test="access-default-empty">
        Sin ninguna base marcada, nadie sin grupo ni regla propia podrá consultar.
      </Alert>
    </Card>

    <Card
      title="Grupos"
      description="Personas que comparten bases y, si querés, un tope mensual de IA. Quien está en varios grupos recibe la unión de sus bases y el mayor de sus topes."
    >
      <div v-if="form.values.groups.length" class="access__items">
        <article
          v-for="(g, index) in form.values.groups"
          :key="g.id ?? g.name"
          class="access__item"
          data-test="access-group"
        >
          <header class="access__item-head">
            <span class="access__item-icon" aria-hidden="true"><UsersRound :size="16" /></span>
            <strong>{{ g.name }}</strong>
            <Badge>{{ g.members.length }} {{ g.members.length === 1 ? 'persona' : 'personas' }}</Badge>
            <Badge tone="info">{{ g.databases.length }} {{ g.databases.length === 1 ? 'base' : 'bases' }}</Badge>
            <Button
              variant="ghost"
              size="sm"
              icon
              class="access__remove"
              :aria-label="`Quitar el grupo ${g.name}`"
              @click="form.values.groups.splice(index, 1)"
            >
              <Trash2 :size="14" aria-hidden="true" />
            </Button>
          </header>
          <div class="access__item-body">
            <section>
              <p class="access__label">Personas</p>
              <div class="access__checks">
                <Checkbox
                  v-for="p in people"
                  :key="p.user_ref"
                  :model-value="g.members.includes(p.user_ref)"
                  :label="p.label ?? `${p.user_ref.slice(0, 8)}…`"
                  :data-test="`access-group-${g.name}-person-${p.user_ref}`"
                  @update:model-value="g.members = toggle(g.members, p.user_ref, $event)"
                />
                <p v-if="!people.length" class="muted">Todavía no hay personas con consumo registrado.</p>
              </div>
            </section>
            <section>
              <p class="access__label">Bases</p>
              <div class="access__checks">
                <Checkbox
                  v-for="d in databases"
                  :key="d.database_ref"
                  :model-value="g.databases.includes(d.database_ref)"
                  :label="d.name"
                  :description="d.code"
                  :data-test="`access-group-${g.name}-db-${d.database_ref}`"
                  @update:model-value="g.databases = toggle(g.databases, d.database_ref, $event)"
                />
                <p v-if="!databases.length" class="muted">Sin bases reportadas.</p>
              </div>
            </section>
            <TextField
              v-model="g.cap"
              class="access__cap"
              label="Tope mensual de IA por persona (USD)"
              inputmode="decimal"
              placeholder="Sin tope"
              :error="form.errors.value[`groups.${index}.cap`]"
              :data-test="`access-group-${g.name}-cap`"
              @blur="form.touch(`groups.${index}.cap`)"
            />
          </div>
        </article>
      </div>
      <EmptyState v-else title="Sin grupos" description="Creá uno para asignar bases a varias personas juntas." />
      <form class="access__add" novalidate @submit.prevent="addGroup">
        <TextField
          v-model="newGroupName"
          label="Nuevo grupo"
          placeholder="Soporte norte"
          :maxlength="80"
          :error="groupError"
          data-test="access-group-name"
        />
        <Button type="submit" variant="secondary" class="access__add-button" data-test="access-group-add">
          Agregar grupo
        </Button>
      </form>
    </Card>

    <Card
      title="Reglas por persona"
      description="Reemplazan los grupos y la regla general para esa persona. Sin ninguna base marcada, la persona no consulta."
    >
      <div v-if="form.values.rules.length" class="access__items">
        <article v-for="r in form.values.rules" :key="r.user_ref" class="access__item" data-test="access-rule">
          <header class="access__item-head">
            <span class="access__item-icon" aria-hidden="true"><UserRound :size="16" /></span>
            <strong>{{ personLabel(r.user_ref) }}</strong>
            <Badge tone="info">{{ r.databases.length }} {{ r.databases.length === 1 ? 'base' : 'bases' }}</Badge>
            <Button
              variant="ghost"
              size="sm"
              icon
              class="access__remove"
              :aria-label="`Quitar la regla de ${personLabel(r.user_ref)}`"
              @click="form.values.rules = form.values.rules.filter((x) => x.user_ref !== r.user_ref)"
            >
              <Trash2 :size="14" aria-hidden="true" />
            </Button>
          </header>
          <div class="access__checks access__item-body">
            <Checkbox
              v-for="d in databases"
              :key="d.database_ref"
              :model-value="r.databases.includes(d.database_ref)"
              :label="d.name"
              :description="d.code"
              :data-test="`access-rule-${r.user_ref}-${d.database_ref}`"
              @update:model-value="r.databases = toggle(r.databases, d.database_ref, $event)"
            />
          </div>
        </article>
      </div>
      <EmptyState v-else title="Sin reglas propias" description="Todas las personas siguen sus grupos o la regla general." />
      <Alert v-if="hasEmptyRule" tone="warning" class="access__alert" data-test="access-rule-empty">
        Hay reglas sin ninguna base: esas personas no podrán consultar.
      </Alert>
      <div class="access__add">
        <Select
          v-model="newRef"
          label="Persona"
          placeholder="Elegí una persona"
          :options="candidates"
          data-test="access-rule-person"
        />
        <Button variant="secondary" class="access__add-button" :disabled="!newRef" data-test="access-rule-add" @click="addRule">
          Agregar regla
        </Button>
      </div>
    </Card>

    <UnsavedBar
      :visible="form.isDirty.value"
      :saving="busy"
      save-label="Guardar reglas"
      @save="askToSave"
      @discard="form.reset()"
    />

    <ConfirmDialog
      :open="confirming"
      title="Guardar las bases por persona"
      message="Las instalaciones de este cliente aplicarán estas reglas en su próximo contacto. Quien no tenga la base asignada no podrá consultarla desde SAVI."
      confirm-label="Guardar reglas"
      :busy="busy"
      @confirm="save"
      @cancel="confirming = false"
    />
  </div>
</template>

<style scoped>
.access {
  display: grid;
  gap: var(--space-6);
}

.access__dbs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-1) var(--space-5);
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border);
}

.access__alert {
  margin-top: var(--space-5);
}

.access__items {
  display: grid;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.access__item {
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
}

.access__item-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  font-size: 13.5px;
}

.access__item-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.access__remove {
  margin-left: auto;
}

.access__item-body {
  display: grid;
  gap: var(--space-5);
  padding: var(--space-4);
}

.access__label {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
}

.access__checks {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 0 var(--space-5);
}

.access__cap {
  max-width: 320px;
}

.access__add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--space-4);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
}

.access__add-button {
  margin-top: 21px;
}

@media (max-width: 600px) {
  .access__add {
    grid-template-columns: minmax(0, 1fr);
  }

  .access__add-button {
    margin-top: 0;
  }
}
</style>
