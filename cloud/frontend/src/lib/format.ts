/** Formateo de cifras y fechas de la consola (es-CO, zona America/Bogota). */

const ZONE = 'America/Bogota'

export type Tone = 'ok' | 'warn' | 'bad' | 'muted'

/** Tono de la consola → tono del `Badge` compartido. */
export function badgeTone(tone: Tone): 'success' | 'warning' | 'danger' | 'neutral' {
  return ({ ok: 'success', warn: 'warning', bad: 'danger', muted: 'neutral' } as const)[tone]
}

export function formatInt(value: number): string {
  return new Intl.NumberFormat('es-CO').format(value)
}

export function formatUsd(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(number)) return '—'
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: number !== 0 && Math.abs(number) < 1 ? 4 : 2,
  }).format(number)
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('es-CO', { style: 'percent', maximumFractionDigits: 1 }).format(
    value,
  )
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 1000) return `${value} ms`
  const seconds = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 }).format(value / 1000)
  return `${seconds} s`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: ZONE,
  }).format(new Date(value))
}

export function formatDay(value: string): string {
  // `YYYY-MM-DD` ya es el día en Bogotá: se arma sin pasar por zonas horarias.
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

/** «hace 3 min», «hace 2 h», «hace 4 días». */
export function relativeTime(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return 'nunca'
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(value).getTime()) / 1000))
  return `hace ${durationLabel(seconds)}`
}

export function durationLabel(seconds: number): string {
  if (seconds < 60) return 'menos de un minuto'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours} h`
  return `${Math.round(hours / 24)} días`
}

/** Frescura de los datos (§7.3): ámbar pasada 1 h, rojo pasadas 24 h. */
export function freshnessTone(seconds: number | null): Tone {
  if (seconds === null) return 'muted'
  if (seconds >= 24 * 3600) return 'bad'
  if (seconds >= 3600) return 'warn'
  return 'ok'
}

export function freshnessLabel(seconds: number | null): string {
  if (seconds === null) return 'Sin datos todavía'
  return `Datos hasta hace ${durationLabel(seconds)}`
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  soporte: 'Soporte',
  comercial: 'Comercial',
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}

const INSTANCE_STATUS: Record<string, string> = {
  active: 'Activa',
  suspended: 'Suspendida',
  revoked: 'Revocada',
}

export function instanceStatusLabel(status: string): string {
  return INSTANCE_STATUS[status] ?? status
}

const REASONS: Record<string, string> = {
  manual: 'Suspendida a mano',
  fingerprint_mismatch: 'La huella cambió (posible copia)',
  client_suspended: 'Cliente suspendido',
}

export function reasonLabel(reason: string | null): string {
  return reason ? (REASONS[reason] ?? reason) : '—'
}

/**
 * Estado visible de una instancia: suspendida/revocada manda sobre la conexión.
 * Una vinculada que todavía no habló con Cloud no está "sin conexión": nunca se
 * conectó, y eso se resuelve distinto (revisar la instalación, no la red).
 */
export function instanceState(instance: {
  status: string
  online: boolean
  last_seen_at?: string | null
}): {
  label: string
  tone: Tone
} {
  if (instance.status !== 'active') {
    return { label: instanceStatusLabel(instance.status), tone: 'bad' }
  }
  if (instance.online) return { label: 'En línea', tone: 'ok' }
  if (instance.last_seen_at === null) return { label: 'Nunca se conectó', tone: 'bad' }
  return { label: 'Sin conexión', tone: 'warn' }
}

// ── Nombres de negocio ────────────────────────────────────────────────────
// La consola muestra lo que la persona del staff reconoce; el valor técnico
// queda en el `title` para soporte.

const DEPLOYMENT_MODES: Record<string, string> = {
  server: 'Servidor',
  desktop: 'Equipo de escritorio',
}

export function deploymentModeLabel(mode: string | null | undefined): string {
  return mode ? (DEPLOYMENT_MODES[mode] ?? mode) : '—'
}

const DB_ENGINES: Record<string, string> = {
  postgresql: 'PostgreSQL',
  sqlite: 'SQLite (archivo local)',
}

export function dbEngineLabel(engine: string | null | undefined): string {
  return engine ? (DB_ENGINES[engine] ?? engine) : '—'
}

const PROVIDERS: Record<string, string> = {
  claude: 'Claude',
  anthropic: 'Claude',
  openai: 'OpenAI',
  gemini: 'Gemini',
}

export function providerLabel(provider: string | null | undefined): string {
  return provider ? (PROVIDERS[provider] ?? provider) : '—'
}

const TOOLS: Record<string, string> = {
  consultar_datos: 'Consultas del ERP',
  consultar_libre: 'Consultas libres',
  consultar_conocimiento: 'Conocimiento del ERP',
  info_empresa: 'Datos de la empresa',
  entregar_archivo: 'Archivos generados',
}

export function toolLabel(name: string): string {
  return TOOLS[name] ?? name
}

const AUDIT_ACTIONS: Record<string, string> = {
  'auth.login': 'Inició sesión',
  'auth.login_failed': 'Intento de ingreso fallido',
  'auth.logout': 'Cerró sesión',
  'auth.mfa_enabled': 'Activó la verificación en dos pasos',
  'auth.mfa_failed': 'Código de verificación incorrecto',
  'auth.mfa_setup_failed': 'Falló la configuración de la verificación',
  'auth.refresh_reuse_detected': 'Sesión reutilizada: se cerró por seguridad',
  'alert.acknowledge': 'Reconoció una alerta',
  'alert.resolve': 'Resolvió una alerta',
  'alert_rule.update': 'Cambió una regla de alerta',
  'client.create': 'Creó un cliente',
  'client.update': 'Editó un cliente',
  'client.suspend': 'Suspendió un cliente',
  'client.activate': 'Reactivó un cliente',
  'client.policy': 'Cambió la política de las instalaciones',
  'client.ai_policy': 'Cambió los límites de IA',
  'client.access_policy': 'Cambió las bases por persona',
  'client.subscription': 'Cambió el plan',
  'client.ledger_entry': 'Registró un movimiento',
  'instance.suspend': 'Suspendió una instalación',
  'instance.activate': 'Reactivó una instalación',
  'instance.revoke': 'Revocó una instalación',
  'instance.request_rotation': 'Pidió renovar credenciales',
  'instance.confirm_fingerprint': 'Confirmó la huella de una instalación',
  'staff.create': 'Creó un usuario del equipo',
  'staff.update': 'Editó un usuario del equipo',
  'staff.activate': 'Reactivó un usuario del equipo',
  'staff.deactivate': 'Desactivó un usuario del equipo',
  'staff.reset_mfa': 'Restableció la verificación de un usuario',
  'token.create': 'Generó un token de vinculación',
  'token.revoke': 'Revocó un token de vinculación',
}

export function auditActionLabel(action: string): string {
  return AUDIT_ACTIONS[action] ?? action
}

/** Opciones del filtro de auditoría, ordenadas por nombre. */
export const AUDIT_ACTION_OPTIONS: { value: string; label: string }[] = Object.entries(
  AUDIT_ACTIONS,
)
  .map(([value, label]) => ({ value, label }))
  .sort((a, b) => a.label.localeCompare(b.label, 'es'))

/** Quién hizo algo: la línea de comandos del servidor no es una persona. */
export function authorLabel(author: string | null | undefined): string {
  if (!author) return '—'
  return author === 'cloud-admin' ? 'Línea de comandos' : author
}

export const SEVERITY: Record<'info' | 'warning' | 'critical', { label: string; tone: Tone }> = {
  info: { label: 'Info', tone: 'muted' },
  warning: { label: 'Aviso', tone: 'warn' },
  critical: { label: 'Crítica', tone: 'bad' },
}

export const ALERT_STATUS: Record<'open' | 'acknowledged' | 'resolved', string> = {
  open: 'Abierta',
  acknowledged: 'Reconocida',
  resolved: 'Resuelta',
}

// ── Resumen y listas ──────────────────────────────────────────────────────

/**
 * Variación frente al periodo anterior. `null` cuando no hay base para comparar
 * (el periodo anterior fue cero): un "+∞ %" no le dice nada a nadie.
 */
export function variation(
  current: number,
  previous: number | null | undefined,
): { text: string; direction: 'up' | 'down' | 'flat' } | null {
  if (previous === null || previous === undefined || previous === 0) return null
  const change = (current - previous) / previous
  if (Math.abs(change) < 0.005) return { text: 'Sin cambio', direction: 'flat' }
  const pct = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 }).format(
    Math.abs(change) * 100,
  )
  return change > 0
    ? { text: `+${pct} %`, direction: 'up' }
    : { text: `−${pct} %`, direction: 'down' }
}

/** Una etiqueta por caso, en vez de "0 / 0" y "nunca". */
export function instancesSummary(client: {
  instances_total: number
  instances_online: number
  instances_waiting?: number
  instances_offline?: number
}): { label: string; tone: Tone } {
  const waiting = client.instances_waiting ?? 0
  const offline = client.instances_offline ?? 0
  if (client.instances_total === 0) return { label: 'Sin instalaciones', tone: 'muted' }
  if (offline > 0) {
    return { label: offline === 1 ? '1 sin conexión' : `${offline} sin conexión`, tone: 'warn' }
  }
  if (client.instances_online === 0 && waiting > 0) {
    return { label: 'Esperando primera conexión', tone: 'muted' }
  }
  if (client.instances_online === client.instances_total) {
    return {
      label: client.instances_total === 1 ? 'En línea' : `${client.instances_total} en línea`,
      tone: 'ok',
    }
  }
  return { label: `${client.instances_online} de ${client.instances_total} en línea`, tone: 'ok' }
}

export const HEALTH: Record<'ok' | 'info' | 'warning' | 'critical', string> = {
  ok: 'Sin pendientes',
  info: 'Para revisar',
  warning: 'Requiere atención',
  critical: 'Urgente',
}

const PLAN_STATUS: Record<string, string> = {
  expiring: 'por vencer',
  expired: 'vencido',
}

/** "Empresarial · vence 30 nov." o "Empresarial · vencido". */
export function planSummary(plan: {
  name: string | null
  valid_until: string | null
  status: string
}): { name: string; detail: string; tone: Tone } {
  const name = plan.name ?? 'Sin nombre'
  if (plan.status === 'expired') return { name, detail: 'Vencido', tone: 'bad' }
  if (!plan.valid_until) return { name, detail: 'Sin vencimiento', tone: 'muted' }
  const day = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short' }).format(
    new Date(`${plan.valid_until}T12:00:00`),
  )
  const tone: Tone = plan.status === 'expiring' ? 'warn' : 'muted'
  const prefix = PLAN_STATUS[plan.status] ? 'Vence pronto: ' : 'Vence '
  return { name, detail: `${prefix}${day}`, tone }
}
