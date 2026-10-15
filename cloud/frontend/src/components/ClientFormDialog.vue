<script setup lang="ts">
import { Button, Dialog, TextField, toast, useZodForm } from '@savi/ui'
import { computed, watch } from 'vue'
import { consoleApi } from '@/lib/api'
import { ApiError } from '@/lib/http'
import { createClientSchema, editClientSchema } from '@/lib/schemas/client'
import type { Client } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

/** Alta de un cliente (sin `client`) o edición de su nombre y NIT (con `client`). */
const props = defineProps<{ open: boolean; client?: Client | null }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; saved: [client: Client] }>()

const isEdit = computed(() => !!props.client)

const create = useZodForm(createClientSchema, { code: '', name: '', nit: '' })
const edit = useZodForm(editClientSchema, { name: '', nit: '' })

watch(
  () => props.open,
  (open) => {
    if (!open) return
    create.reset({ code: '', name: '', nit: '' })
    edit.reset({ name: props.client?.name ?? '', nit: props.client?.nit ?? '' })
  },
  { immediate: true },
)

const submitting = computed(() => create.submitting.value || edit.submitting.value)

function close(): void {
  emit('update:open', false)
}

async function submit(): Promise<void> {
  if (isEdit.value && props.client) {
    const id = props.client.id
    await edit.handleSubmit(async (data) => {
      try {
        const saved = await consoleApi.updateClient(id, data)
        toast.success('Cliente actualizado')
        emit('saved', saved)
        close()
      } catch (e) {
        toast.error('No se pudo guardar el cliente', { description: errorMessage(e) })
      }
    })
    return
  }
  await create.handleSubmit(async (data) => {
    try {
      const saved = await consoleApi.createClient(data)
      toast.success(`Cliente ${saved.code} creado`)
      emit('saved', saved)
      close()
    } catch (e) {
      // Código repetido: el error va al campo, que es donde se corrige.
      if (
        e instanceof ApiError &&
        (e.code === 'client_code_already_exists' || e.code === 'invalid_client_code')
      ) {
        create.setServerErrors({ code: e.message })
      } else {
        toast.error('No se pudo crear el cliente', { description: errorMessage(e) })
      }
    }
  })
}
</script>

<template>
  <Dialog
    :open="open"
    :title="isEdit ? 'Editar cliente' : 'Nuevo cliente'"
    :description="
      isEdit
        ? 'El código no se puede cambiar: lo usan las instalaciones vinculadas.'
        : 'Una empresa que usa SAVI. Después vas a poder vincular sus instalaciones.'
    "
    :max-width="480"
    @update:open="emit('update:open', $event)"
  >
    <form id="client-form" class="client-form" novalidate @submit.prevent="submit">
      <TextField
        v-if="!isEdit"
        v-model="create.values.code"
        label="Código"
        required
        mono
        placeholder="FARMX"
        :maxlength="32"
        hint="Mayúsculas, números o guion bajo. No se puede cambiar después."
        :error="create.errors.value.code"
        data-test="client-code"
        @blur="create.touch('code')"
      />
      <template v-if="isEdit">
        <TextField
          v-model="edit.values.name"
          label="Nombre"
          required
          :maxlength="200"
          :error="edit.errors.value.name"
          data-test="client-name"
          @blur="edit.touch('name')"
        />
        <TextField
          v-model="edit.values.nit"
          label="NIT"
          placeholder="Opcional"
          :maxlength="32"
          :error="edit.errors.value.nit"
          data-test="client-nit"
          @blur="edit.touch('nit')"
        />
      </template>
      <template v-else>
        <TextField
          v-model="create.values.name"
          label="Nombre"
          required
          placeholder="Farmacias X S.A.S."
          :maxlength="200"
          :error="create.errors.value.name"
          data-test="client-name"
          @blur="create.touch('name')"
        />
        <TextField
          v-model="create.values.nit"
          label="NIT"
          placeholder="Opcional"
          :maxlength="32"
          :error="create.errors.value.nit"
          data-test="client-nit"
          @blur="create.touch('nit')"
        />
      </template>
    </form>
    <template #footer>
      <Button variant="ghost" :disabled="submitting" @click="close">Cancelar</Button>
      <Button type="submit" form="client-form" :loading="submitting" data-test="client-save">
        {{ isEdit ? 'Guardar cambios' : 'Crear cliente' }}
      </Button>
    </template>
  </Dialog>
</template>

<style scoped>
.client-form {
  display: grid;
  gap: var(--space-5);
}
</style>
