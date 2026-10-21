/**
 * Reglas puras de qué mostrar. Sin Vue ni red, para probarlas sin montar nada.
 */
import type { ApplyPhase, UpdateNoticeKind, UpdateStatus } from '../types'

/** "Más tarde" oculta el aviso por 24 h (spec 09, sección 6). */
export const SNOOZE_MS = 24 * 60 * 60 * 1000

const ACTIVE_PHASES: readonly ApplyPhase[] = ['downloading', 'waiting_turns', 'installing']

export function isApplying(status: UpdateStatus): boolean {
  return ACTIVE_PHASES.includes(status.phase)
}

export function noticeKind(
  status: UpdateStatus | null,
  now: number,
  snoozedUntil: number | null,
): UpdateNoticeKind {
  if (status === null || !status.enabled) return 'none'
  if (isApplying(status)) return 'progress'
  if (status.state === 'blocked') return 'blocked'
  if (status.state === 'up_to_date') return 'none'
  // Si falló, el aviso vuelve aunque se haya pospuesto: tiene el botón Reintentar.
  if (status.phase === 'failed') return 'banner'
  if (snoozedUntil !== null && now < snoozedUntil) return 'none'
  return 'banner'
}

export function progressPercent(status: UpdateStatus): number | null {
  if (status.size === null || status.size <= 0) return null
  return Math.min(100, Math.floor((status.downloaded_bytes / status.size) * 100))
}

export function formatDeadline(iso: string): string {
  return new Intl.DateTimeFormat('es-CO', {
    day: 'numeric',
    month: 'long',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

export function bannerMessage(status: UpdateStatus): string {
  const version = status.available_version ?? ''
  if (status.state === 'required' && status.deadline !== null) {
    return `Debe actualizar SAVI a la versión ${version} antes del ${formatDeadline(status.deadline)}.`
  }
  return `Hay una versión nueva de SAVI (${version}).`
}

export function progressMessage(status: UpdateStatus): string {
  if (status.phase === 'waiting_turns') {
    return 'Esperando a que terminen las respuestas en curso…'
  }
  if (status.phase === 'installing') return 'Instalando la actualización y reiniciando SAVI…'
  const percent = progressPercent(status)
  return percent === null
    ? 'Descargando la actualización…'
    : `Descargando la actualización… ${percent} %`
}

/** El backend respondió con otra versión: el instalador terminó. */
export function restartedWithNewVersion(
  healthVersion: string | null,
  previous: string | null,
): boolean {
  return healthVersion !== null && previous !== null && healthVersion !== previous
}
