<script setup lang="ts">
import { ref } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { consoleApi } from '@/lib/api'
import type { Client } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; client: Client }>()
const emit = defineEmits<{ saved: [] }>()

type PolicyChange = 'lock' | 'unlock' | 'named' | 'pseudonym' | 'cli_on' | 'cli_off'
const policyChange = ref<PolicyChange | null>(null)
const policyBusy = ref(false)
const policyError = ref<string | null>(null)

const POLICY_COPY: Record<PolicyChange, { title: string; message: string; confirm: string }> = {
  lock: {
    title: 'Dejar las instalaciones solo con el chat',
    message:
      'En cada equipo de este cliente se oculta Administración y se rechaza cualquier cambio de configuración. Aplica en el próximo contacto de cada instalación.',
    confirm: 'Bloquear configuración',
  },
  unlock: {
    title: 'Permitir configurar las instalaciones',
    message:
      'Las personas administradoras de cada equipo vuelven a ver Administración. Aplica en el próximo contacto.',
    confirm: 'Permitir configuración',
  },
  named: {
    title: 'Identificar a las personas por su usuario',
    message:
      'Cloud va a guardar el código de usuario de quienes inician sesión (por ejemplo JPEREZ), no solo un seudónimo. Corresponde a la organización interna: no lo actives para un cliente que no lo autorizó.',
    confirm: 'Identificar personas',
  },
  cli_on: {
    title: 'Permitir el CLI de Claude en las instalaciones',
    message:
      'Quien administre una instalación local podrá usar la sesión de Claude iniciada en su equipo, con su propia cuenta. El consumo de esa cuenta no pasa por SEO Group. Aplica en el próximo contacto.',
    confirm: 'Permitir CLI de Claude',
  },
  cli_off: {
    title: 'Dejar de permitir el CLI de Claude',
    message:
      'Las instalaciones que lo estén usando dejan de responder en el turno siguiente hasta que se configure otro proveedor de IA.',
    confirm: 'No permitir',
  },
  pseudonym: {
    title: 'Volver a seudónimos',
    message:
      'Las instalaciones dejan de enviar el código de usuario. Los ya guardados se conservan hasta que venzan.',
    confirm: 'Usar seudónimos',
  },
}

async function applyPolicy(): Promise<void> {
  const change = policyChange.value
  if (!change) return
  policyBusy.value = true
  policyError.value = null
  try {
    await consoleApi.setClientPolicy(
      props.clientId,
      change === 'lock' || change === 'unlock'
        ? { config_locked: change === 'lock' }
        : change === 'cli_on' || change === 'cli_off'
          ? { allow_local_cli: change === 'cli_on' }
          : { identity_mode: change },
    )
    emit('saved')
  } catch (e) {
    policyError.value = errorMessage(e)
  } finally {
    policyBusy.value = false
    policyChange.value = null
  }
}
</script>

<template>
<section class="card policy" data-test="client-policy">
  <h2>Política de las instalaciones</h2>
  <p v-if="policyError" class="error-text" role="alert">{{ policyError }}</p>
  <div class="policy__row">
    <div>
      <strong>Configuración</strong>
      <p class="muted">
        {{
          client.config_locked
            ? 'Bloqueada: cada equipo queda solo con el chat.'
            : 'Libre: las personas administradoras de cada equipo pueden configurar.'
        }}
      </p>
    </div>
    <button
      class="btn btn-small"
      type="button"
      data-test="toggle-lock"
      @click="policyChange = client.config_locked ? 'unlock' : 'lock'"
    >
      {{ client.config_locked ? 'Permitir configuración' : 'Bloquear configuración' }}
    </button>
  </div>
  <div class="policy__row">
    <div>
      <strong>Identidad de las personas</strong>
      <p class="muted">
        {{
          client.identity_mode === 'named'
            ? 'Por código de usuario (organización interna).'
            : 'Por seudónimo: Cloud no sabe quiénes son.'
        }}
      </p>
    </div>
    <button
      class="btn btn-small"
      type="button"
      data-test="toggle-identity"
      @click="policyChange = client.identity_mode === 'named' ? 'pseudonym' : 'named'"
    >
      {{ client.identity_mode === 'named' ? 'Usar seudónimos' : 'Identificar personas' }}
    </button>
  </div>
  <div class="policy__row">
    <div>
      <strong>CLI de Claude en el equipo</strong>
      <p class="muted">
        {{
          client.allow_local_cli
            ? 'Permitido: la instalación local puede usar la sesión de Claude de la persona.'
            : 'No permitido: solo se usan las claves que configure el administrador.'
        }}
      </p>
    </div>
    <button
      class="btn btn-small"
      type="button"
      data-test="toggle-cli"
      @click="policyChange = client.allow_local_cli ? 'cli_off' : 'cli_on'"
    >
      {{ client.allow_local_cli ? 'No permitir' : 'Permitir CLI de Claude' }}
    </button>
  </div>
</section>

<ConfirmDialog
  :open="policyChange !== null"
  :title="policyChange ? POLICY_COPY[policyChange].title : ''"
  :message="policyChange ? POLICY_COPY[policyChange].message : ''"
  :confirm-label="policyChange ? POLICY_COPY[policyChange].confirm : 'Confirmar'"
  :danger="policyChange === 'lock' || policyChange === 'named' || policyChange === 'cli_on'"
  :busy="policyBusy"
  @confirm="applyPolicy"
  @cancel="policyChange = null"
/>
</template>

<style scoped>
.policy {
  display: grid;
  gap: 0.8rem;
}
.policy__row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
}
.policy__row p {
  margin: 0.15rem 0 0;
}
</style>
