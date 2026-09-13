<script setup lang="ts">
/**
 * Alta y edición de una base del ERP.
 *
 * "Probar conexión" es independiente de guardar; el backend además vuelve
 * a probar antes de persistir y responde 422 si falla. Al editar, la
 * contraseña arranca vacía y solo se envía si se escribe una nueva.
 */
import { computed, ref, useId, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { toast } from '@/lib/toast'
import { erpDatabaseService } from '../services/erpDatabaseService'
import { useErpDatabaseStore } from '../stores/erpDatabaseStore'
import type { ConnectionTestResult, ErpDatabase, ErpDatabaseFormValues } from '../types'
import {
  emptyFormValues,
  formValuesFrom,
  toSaveRequest,
  validateFormValues,
} from '../utils/erpDatabaseForm'

const props = defineProps<{
  open: boolean
  database: ErpDatabase | null
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const store = useErpDatabaseStore()
const uid = useId()

const values = ref<ErpDatabaseFormValues>(emptyFormValues())
const formError = ref<string | null>(null)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<ConnectionTestResult | null>(null)

const isEdit = computed(() => props.database !== null)
const title = computed(() => (isEdit.value ? 'Editar base de datos' : 'Nueva base de datos'))

watch(
  () => props.open,
  (open) => {
    if (!open) return
    values.value = props.database ? formValuesFrom(props.database) : emptyFormValues()
    formError.value = null
    testResult.value = null
  },
  { immediate: true },
)

function close(): void {
  emit('update:open', false)
}

async function onTest(): Promise<void> {
  // El nombre no se exige para probar: una prueba exitosa lo propone.
  formError.value = validateFormValues(values.value, {
    requirePassword: !isEdit.value,
    requireName: false,
  })
  if (formError.value) return
  testing.value = true
  testResult.value = null
  try {
    // El backend valida el request completo aunque no persista nada.
    const request = toSaveRequest(values.value)
    const result = await erpDatabaseService.testConnection(
      { ...request, name: request.name || request.code },
      props.database?.id,
    )
    testResult.value = result
    if (result.ok && result.razon_social && !values.value.name.trim()) {
      values.value.name = result.razon_social
    }
  } catch (e) {
    formError.value = (e as Error).message || 'No se pudo probar la conexión.'
  } finally {
    testing.value = false
  }
}

async function onSubmit(): Promise<void> {
  formError.value = validateFormValues(values.value, { requirePassword: !isEdit.value })
  if (formError.value) return
  saving.value = true
  try {
    if (props.database) {
      await store.update(props.database.id, values.value)
      toast.success('Base de datos actualizada')
    } else {
      await store.create(values.value)
      toast.success('Base de datos registrada')
    }
    close()
  } catch (e) {
    formError.value = (e as Error).message || 'No se pudo guardar la base de datos.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="open" :title="title" :max-width="560" :close-on-overlay="false" @update:open="emit('update:open', $event)">
    <form id="erp-database-form" class="dbform" novalidate @submit.prevent="onSubmit">
      <div class="dbform__grid">
        <label class="dbform__field">
          <span class="dbform__label">Código</span>
          <input v-model="values.code" class="dbform__input dbform__input--mono" maxlength="32" autocomplete="off" required :aria-describedby="`${uid}-code`" />
        </label>
        <label class="dbform__field">
          <span class="dbform__label">Nombre</span>
          <input v-model="values.name" class="dbform__input" maxlength="120" autocomplete="off" required :aria-describedby="`${uid}-name`" />
        </label>
        <p :id="`${uid}-code`" class="dbform__hint">
          Se escribe después de la @ al iniciar sesión (ej. USUARIO@{{ values.code.toUpperCase() || 'CODIGO' }}).
        </p>
        <p :id="`${uid}-name`" class="dbform__hint">
          Si lo dejas vacío, se propone la razón social al probar la conexión.
        </p>
        <label class="dbform__field dbform__field--wide">
          <span class="dbform__label">Host</span>
          <input v-model="values.host" class="dbform__input dbform__input--mono" autocomplete="off" required />
        </label>
        <label class="dbform__field">
          <span class="dbform__label">Puerto</span>
          <input v-model.number="values.port" type="number" min="1" max="65535" class="dbform__input" required />
        </label>
        <label class="dbform__field">
          <span class="dbform__label">Base de datos</span>
          <input v-model="values.database" class="dbform__input dbform__input--mono" autocomplete="off" required />
        </label>
        <label class="dbform__field">
          <span class="dbform__label">Usuario</span>
          <input v-model="values.username" class="dbform__input dbform__input--mono" autocomplete="off" required />
        </label>
        <label class="dbform__field">
          <span class="dbform__label">Contraseña</span>
          <input
            v-model="values.password"
            type="password"
            class="dbform__input"
            autocomplete="new-password"
            :placeholder="isEdit ? 'Déjala vacía para conservar la actual' : ''"
          />
        </label>
        <label class="dbform__field">
          <span class="dbform__label">Tiempo máximo de consulta (ms)</span>
          <input v-model.number="values.statement_timeout_ms" type="number" min="1000" max="600000" step="1000" class="dbform__input" required />
        </label>
      </div>

      <div
        v-if="testResult"
        class="dbform__result"
        :class="testResult.ok ? 'dbform__result--ok' : 'dbform__result--fail'"
        role="status"
      >
        <template v-if="testResult.ok">
          <strong>Conexión exitosa.</strong>
          <span v-if="testResult.razon_social"> Empresa: {{ testResult.razon_social }}</span>
        </template>
        <template v-else>
          <strong>No se pudo conectar.</strong> {{ testResult.detail }}
          <span v-if="testResult.missing_tables.length > 0" class="dbform__missing">
            Tablas faltantes: {{ testResult.missing_tables.join(', ') }}
          </span>
        </template>
      </div>

      <p v-if="formError" class="dbform__error" role="alert">{{ formError }}</p>
    </form>

    <template #footer>
      <Button variant="secondary" :loading="testing" :disabled="saving" @click="onTest">
        Probar conexión
      </Button>
      <span class="dbform__spacer" />
      <Button variant="ghost" :disabled="saving" @click="close">Cancelar</Button>
      <Button type="submit" form="erp-database-form" :loading="saving" :disabled="testing">
        Guardar
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.dbform__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.dbform__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.dbform__field--wide {
  grid-column: 1 / -1;
}

.dbform__label {
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.dbform__input {
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.dbform__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.dbform__input--mono {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}

.dbform__hint {
  margin: calc(-1 * var(--space-3)) 0 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.4;
}

.dbform__result {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  font-size: 12px;
  line-height: 1.5;
}

.dbform__result--ok {
  background: var(--surface-success, rgba(22, 163, 74, 0.08));
  color: var(--text-success, #15803d);
}

.dbform__result--fail {
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
}

.dbform__missing {
  display: block;
  margin-top: var(--space-1);
  font-family: var(--font-mono, monospace);
}

.dbform__error {
  margin: var(--space-4) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}

.dbform__spacer {
  flex: 1;
}

@media (max-width: 560px) {
  .dbform__grid {
    grid-template-columns: 1fr;
  }
}
</style>
