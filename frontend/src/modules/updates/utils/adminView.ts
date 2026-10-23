/**
 * Textos y reglas de la vista de Administración. Puras, sin Vue ni red.
 */
import type { InstallOutcome, UpdateStatus } from '../types'

/** Evento con el que la vista avisa al aviso global que el estado cambió. */
export const STATUS_CHANGED_EVENT = 'savi:update-status-changed'

const OUTCOME_LABELS: Record<InstallOutcome, string> = {
  installed: 'Instalada',
  rolled_back: 'Revertida',
  failed: 'Falló',
  cancelled: 'Cancelada',
  timeout: 'Sin respuesta',
  interrupted: 'Interrumpida',
}

export function outcomeLabel(outcome: InstallOutcome): string {
  return OUTCOME_LABELS[outcome]
}

export function channelLabel(channel: string): string {
  if (channel === 'stable') return 'Estable'
  if (channel === 'beta') return 'Beta (pruebas de SEO)'
  return channel
}

/** "Actualizar ahora" solo tiene sentido si hay algo para instalar y nada en curso. */
export function canApplyNow(status: UpdateStatus): boolean {
  if (!status.enabled || !status.can_apply) return false
  if (status.state === 'up_to_date') return false
  return status.phase === 'idle' || status.phase === 'failed'
}

/** El aviso global consulta el estado cada 15 min: esto lo hace consultar ya. */
export function notifyStatusChanged(): void {
  window.dispatchEvent(new Event(STATUS_CHANGED_EVENT))
}
