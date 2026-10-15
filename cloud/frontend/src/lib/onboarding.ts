import { roleLabel } from './format'
import type { ClientOnboarding, Permission } from './types'

export interface OnboardingStep {
  key: keyof ClientOnboarding
  label: string
  /** Qué se hace en este paso. */
  hint: string
  done: boolean
  /** Pestaña del cliente donde se completa o se comprueba. */
  tab: string
  /** Rol al que le toca, solo si la persona actual no puede hacerlo. */
  pendingRole: string | null
}

interface StepDefinition {
  key: keyof ClientOnboarding
  label: string
  hint: string
  tab: string
  /** Permiso que exige completar el paso; sin él, el paso no depende de una persona. */
  permission?: Permission
  /** Rol que tiene ese permiso (la matriz vive en el backend). */
  role?: 'admin' | 'soporte' | 'comercial'
}

const DEFINITIONS: StepDefinition[] = [
  {
    key: 'plan_loaded',
    label: 'Plan cargado',
    hint: 'Registra el plan contratado y hasta cuándo está vigente.',
    tab: 'suscripcion',
    permission: 'clients.billing',
    role: 'comercial',
  },
  {
    key: 'policy_defined',
    label: 'Política definida',
    hint: 'Decide cómo se identifica a las personas y qué bases puede consultar cada una.',
    tab: 'politica',
    permission: 'clients.policy',
    role: 'admin',
  },
  {
    key: 'ai_defined',
    label: 'Límites de IA definidos',
    hint: 'Elige los proveedores permitidos y los topes mensuales.',
    tab: 'ia',
    permission: 'clients.policy',
    role: 'admin',
  },
  {
    key: 'token_created',
    label: 'Token de vinculación generado',
    hint: 'Genera el token que se pega en la instalación de SAVI.',
    tab: 'vinculacion',
    permission: 'tokens.manage',
    role: 'soporte',
  },
  {
    key: 'instance_connected',
    label: 'Primera instalación en línea',
    hint: 'Aparece cuando una instalación vinculada contacta a Cloud.',
    tab: 'instancias',
  },
  {
    key: 'report_received',
    label: 'Primer reporte recibido',
    hint: 'Aparece cuando la instalación envía sus sucursales o personas.',
    tab: 'sucursales',
  },
]

/**
 * Pasos de la puesta en marcha con su estado. `can` decide si la persona actual puede completar
 * cada paso: si no puede, el paso queda "Pendiente de <rol>" en vez de apuntar a una acción
 * prohibida.
 */
export function buildOnboardingSteps(
  state: ClientOnboarding,
  can: (permission: Permission) => boolean,
): OnboardingStep[] {
  return DEFINITIONS.map((d) => ({
    key: d.key,
    label: d.label,
    hint: d.hint,
    done: state[d.key],
    tab: d.tab,
    pendingRole:
      !state[d.key] && d.permission && d.role && !can(d.permission) ? roleLabel(d.role) : null,
  }))
}
