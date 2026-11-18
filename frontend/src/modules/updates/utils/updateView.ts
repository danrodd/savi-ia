/**
 * Reglas puras de qué mostrar. Sin Vue ni red, para probarlas sin montar nada.
 */
import type { ApplyPhase, ResultNotice, UpdateNoticeKind, UpdateStatus } from '../types'

/** "Más tarde" oculta el aviso por 24 h (spec 09, sección 6). */
export const SNOOZE_MS = 24 * 60 * 60 * 1000

/** Si pasado este tiempo SAVI no volvió, se avisa en lugar de esperar para siempre. */
export const INSTALLING_MAX_MS = 15 * 60 * 1000

export const STALLED_MESSAGE =
  'La actualización está tardando más de lo normal. Si SAVI no vuelve a abrir, ábralo desde el menú Inicio.'

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

/** `true` si el instalador lleva demasiado tiempo sin que SAVI vuelva. */
export function installStalled(since: number | null, now: number): boolean {
  return since !== null && now - since > INSTALLING_MAX_MS
}

/**
 * Aviso del último intento de instalación, una sola vez por intento.
 *
 * No se repite lo que la persona ya vio: la cancelación del permiso se mostró en
 * el momento, y un intento que falló en esta misma sesión ya tiene su mensaje en
 * la barra.
 */
export function resultNotice(
  status: UpdateStatus | null,
  seenAttemptId: string | null,
): ResultNotice | null {
  const last = status?.last_install ?? null
  if (status === null || !status.enabled || last === null) return null
  if (last.attempt_id === seenAttemptId) return null
  if (isApplying(status) || status.phase === 'failed') return null
  if (last.outcome === 'cancelled') return null
  return {
    tone: last.outcome === 'installed' ? 'success' : 'warning',
    message: last.message,
    attemptId: last.attempt_id,
  }
}
