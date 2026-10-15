<script setup lang="ts">
import { Badge, Button, Card, toast } from '@savi/ui'
import { Fingerprint, Lock, TerminalSquare } from 'lucide-vue-next'
import { type Component, computed, ref } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { consoleApi } from '@/lib/api'
import type { Client } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; client: Client }>()
const emit = defineEmits<{ saved: [] }>()

type PolicyChange = 'lock' | 'unlock' | 'named' | 'pseudonym' | 'cli_on' | 'cli_off'
const policyChange = ref<PolicyChange | null>(null)
const policyBusy = ref(false)

const POLICY_COPY: Record<
  PolicyChange,
  { title: string; message: string; confirm: string; done: string }
> = {
  lock: {
    title: 'Dejar las instalaciones solo con el chat',
    message:
      'En cada equipo de este cliente se oculta Administración y se rechaza cualquier cambio de configuración. Aplica en el próximo contacto de cada instalación.',
    confirm: 'Bloquear configuración',
    done: 'Configuración bloqueada',
  },
  unlock: {
    title: 'Permitir configurar las instalaciones',
    message:
      'Las personas administradoras de cada equipo vuelven a ver Administración. Aplica en el próximo contacto.',
    confirm: 'Permitir configuración',
    done: 'Configuración permitida',
  },
  named: {
    title: 'Identificar a las personas por su usuario',
    message:
      'Cloud va a guardar el código de usuario de quienes inician sesión (por ejemplo JPEREZ), no solo un seudónimo. Corresponde a la organización interna: no lo actives para un cliente que no lo autorizó.',
    confirm: 'Identificar personas',
    done: 'Ahora se identifica a las personas',
  },
  cli_on: {
    title: 'Permitir el CLI de Claude en las instalaciones',
    message:
      'Quien administre una instalación local podrá usar la sesión de Claude iniciada en su equipo, con su propia cuenta. El consumo de esa cuenta no pasa por SEO Group. Aplica en el próximo contacto.',
    confirm: 'Permitir CLI de Claude',
    done: 'CLI de Claude permitido',
  },
  cli_off: {
    title: 'Dejar de permitir el CLI de Claude',
    message:
      'Las instalaciones que lo estén usando dejan de responder en el turno siguiente hasta que se configure otro proveedor de IA.',
    confirm: 'No permitir',
    done: 'CLI de Claude desactivado',
  },
  pseudonym: {
    title: 'Volver a seudónimos',
    message:
      'Las instalaciones dejan de enviar el código de usuario. Los ya guardados se conservan hasta que venzan.',
    confirm: 'Usar seudónimos',
    done: 'Se volvió a usar seudónimos',
  },
}

interface PolicyRow {
  key: string
  icon: Component
  title: string
  state: string
  tone: 'success' | 'warning' | 'neutral' | 'info'
  description: string
  action: string
  change: PolicyChange
  test: string
}

const rows = computed<PolicyRow[]>(() => [
  {
    key: 'config',
    icon: Lock,
    title: 'Configuración en cada equipo',
    state: props.client.config_locked ? 'Bloqueada' : 'Libre',
    tone: props.client.config_locked ? 'warning' : 'success',
    description: props.client.config_locked
      ? 'Cada equipo queda solo con el chat: no se ve Administración.'
      : 'Las personas administradoras de cada equipo pueden configurar.',
    action: props.client.config_locked ? 'Permitir configuración' : 'Bloquear configuración',
    change: props.client.config_locked ? 'unlock' : 'lock',
    test: 'toggle-lock',
  },
  {
    key: 'identity',
    icon: Fingerprint,
    title: 'Identidad de las personas',
    state: props.client.identity_mode === 'named' ? 'Por usuario' : 'Seudónimo',
    tone: props.client.identity_mode === 'named' ? 'info' : 'neutral',
    description:
      props.client.identity_mode === 'named'
        ? 'Cloud guarda el código de usuario (solo para la organización interna).'
        : 'Cloud no sabe quiénes son: solo ve un seudónimo por persona.',
    action: props.client.identity_mode === 'named' ? 'Usar seudónimos' : 'Identificar personas',
    change: props.client.identity_mode === 'named' ? 'pseudonym' : 'named',
    test: 'toggle-identity',
  },
  {
    key: 'cli',
    icon: TerminalSquare,
    title: 'CLI de Claude en el equipo',
    state: props.client.allow_local_cli ? 'Permitido' : 'No permitido',
    tone: props.client.allow_local_cli ? 'info' : 'neutral',
    description: props.client.allow_local_cli
      ? 'La instalación local puede usar la sesión de Claude de la persona.'
      : 'Solo se usan las claves de IA que configure el administrador.',
    action: props.client.allow_local_cli ? 'No permitir' : 'Permitir CLI de Claude',
    change: props.client.allow_local_cli ? 'cli_off' : 'cli_on',
    test: 'toggle-cli',
  },
])

async function applyPolicy(): Promise<void> {
  const change = policyChange.value
  if (!change) return
  policyBusy.value = true
  try {
    await consoleApi.setClientPolicy(
      props.clientId,
      change === 'lock' || change === 'unlock'
        ? { config_locked: change === 'lock' }
        : change === 'cli_on' || change === 'cli_off'
          ? { allow_local_cli: change === 'cli_on' }
          : { identity_mode: change },
    )
    toast.success(POLICY_COPY[change].done, {
      description: 'Las instalaciones lo aplican en su próximo contacto.',
    })
    emit('saved')
  } catch (e) {
    toast.error('No se pudo cambiar la política', { description: errorMessage(e) })
  } finally {
    policyBusy.value = false
    policyChange.value = null
  }
}
</script>

<template>
  <Card
    title="Política de las instalaciones"
    description="Cómo se comportan los equipos de este cliente. Cada cambio llega en el próximo contacto de cada instalación."
    data-test="client-policy"
  >
    <ul class="policy">
      <li v-for="row in rows" :key="row.key" class="policy__row">
        <span class="policy__icon" aria-hidden="true"><component :is="row.icon" :size="18" /></span>
        <div class="policy__text">
          <div class="policy__title">
            <strong>{{ row.title }}</strong>
            <Badge :tone="row.tone">{{ row.state }}</Badge>
          </div>
          <p>{{ row.description }}</p>
        </div>
        <Button variant="secondary" size="sm" :data-test="row.test" @click="policyChange = row.change">
          {{ row.action }}
        </Button>
      </li>
    </ul>
  </Card>

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
  margin: 0;
  padding: 0;
  list-style: none;
}

.policy__row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-5) 0;
  border-bottom: 1px solid var(--border);
}

.policy__row:first-child {
  padding-top: 0;
}

.policy__row:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.policy__icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: var(--r-md);
  background: var(--surface-subtle);
  color: var(--text-muted);
}

.policy__text {
  flex: 1;
  min-width: 0;
}

.policy__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
  font-size: 13.5px;
}

.policy__text p {
  margin: var(--space-1) 0 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

@media (max-width: 600px) {
  .policy__row {
    flex-wrap: wrap;
  }

  .policy__row :deep(.btn) {
    margin-left: calc(38px + var(--space-4));
  }
}
</style>
