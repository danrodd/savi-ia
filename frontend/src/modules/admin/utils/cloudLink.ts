import type { CloudLinkState, CloudLinkStatus } from '../types'

/** Sin contacto con SAVI Cloud durante este tiempo, el aviso es global (P6). */
export const OFFLINE_ALERT_HOURS = 72

export type StatusTone = 'ok' | 'warn' | 'danger' | 'neutral'

export const CLOUD_STATUS_LABELS: Record<CloudLinkStatus, string> = {
  unlinked: 'Sin vincular',
  linked: 'Conectada',
  offline: 'Sin conexión',
  suspended: 'Suspendida',
  unauthorized: 'Sin autorización',
  revoked: 'Revocada',
}

const STATUS_TONES: Record<CloudLinkStatus, StatusTone> = {
  unlinked: 'neutral',
  linked: 'ok',
  offline: 'warn',
  suspended: 'danger',
  unauthorized: 'danger',
  revoked: 'danger',
}

export function statusTone(status: CloudLinkStatus): StatusTone {
  return STATUS_TONES[status] ?? 'neutral'
}

export const CLOUD_STATUS_HINTS: Partial<Record<CloudLinkStatus, string>> = {
  linked: 'Todo en orden: SAVI está enviando sus datos de uso a SAVI Cloud.',
  offline:
    'SAVI no logra comunicarse con SAVI Cloud. Cuando vuelva la conexión se retoma solo y no se pierde nada.',
  suspended:
    'SEO Group suspendió a su empresa en SAVI Cloud. Comuníquese con SEO Group para reactivarla.',
  unauthorized:
    'SAVI Cloud no reconoce las credenciales de esta instalación. Comuníquese con SEO Group.',
  revoked:
    'SEO Group revocó esta instalación en SAVI Cloud. Desvincúlela y pida un token nuevo para volver a conectarla.',
}

/** Mensajes amigables por `errorCode` del backend (y por status HTTP). */
const ERROR_MESSAGES: Record<string, string> = {
  enrollment_token_invalid: 'El token no existe, venció o ya se usó. Pida uno nuevo a SEO Group.',
  client_suspended: 'La empresa está suspendida en SAVI Cloud. Comuníquese con SEO Group.',
  too_many_requests: 'Hubo demasiados intentos. Espere unos minutos e intente de nuevo.',
  timeout: 'SAVI Cloud no respondió a tiempo. Intente de nuevo en un momento.',
  network_error: 'No se pudo conectar con SAVI Cloud. Revise la conexión a internet.',
  contract_rejected:
    'SAVI Cloud no aceptó la vinculación. Avísele a SEO Group para que revise esta instalación.',
}

const ALREADY_LINKED =
  'Esta instalación ya está vinculada. Desvincúlela primero para usar otro token.'

export function cloudLinkErrorMessage(
  error: unknown,
  fallback = 'No se pudo completar la acción.',
): string {
  const e = error as { status?: number; body?: { errorCode?: string }; message?: string }
  const code = e?.body?.errorCode
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code]
  if (e?.status === 422 && /ya est[aá] vinculada/i.test(e.message ?? '')) return ALREADY_LINKED
  if (e?.status === 429) return ERROR_MESSAGES.too_many_requests as string
  if (e?.status !== undefined && e.status >= 502) return ERROR_MESSAGES.network_error as string
  return e?.message || fallback
}

/** Nombre amigable de cada stream que se sincroniza. */
export const STREAM_LABELS: Record<string, string> = {
  turn: 'Respuestas de SAVI',
  conversation: 'Conversaciones',
  session: 'Sesiones',
  free_query: 'Consultas libres',
  database: 'Bases de datos',
}

export function streamLabel(stream: string): string {
  return STREAM_LABELS[stream] ?? stream
}

/** "al día" si el último envío fue reciente respecto del último contacto; si no, "enviando historial…". */
export function streamProgress(
  stream: { last_ok_at: string | null; watermark_at: string },
  now: Date = new Date(),
): string {
  if (!stream.last_ok_at) return 'enviando historial…'
  const lagMs = now.getTime() - new Date(stream.watermark_at).getTime()
  return lagMs > 24 * 3_600_000 ? 'enviando historial…' : 'al día'
}

/**
 * ¿Hay que avisar en toda la Administración? `offline` hace más de 72 h,
 * o `suspended` / `unauthorized` / `revoked`.
 */
export function needsGlobalAlert(state: CloudLinkState | null, now: Date = new Date()): boolean {
  if (!state) return false
  if (
    state.status === 'suspended' ||
    state.status === 'unauthorized' ||
    state.status === 'revoked'
  ) {
    return true
  }
  if (state.status !== 'offline') return false
  const since = state.last_heartbeat_ok_at ?? state.linked_at
  if (!since) return false
  return now.getTime() - new Date(since).getTime() >= OFFLINE_ALERT_HOURS * 3_600_000
}

export function globalAlertText(state: CloudLinkState): string {
  if (state.status === 'offline') {
    return `SAVI lleva más de ${OFFLINE_ALERT_HOURS} horas sin comunicarse con SAVI Cloud. Revise la conexión a internet de este equipo.`
  }
  if (state.status === 'suspended') {
    return 'La empresa está suspendida en SAVI Cloud. Comuníquese con SEO Group.'
  }
  if (state.status === 'revoked') {
    return 'SEO Group revocó la vinculación de esta instalación con SAVI Cloud. Pida un token nuevo.'
  }
  return 'SAVI Cloud no reconoce las credenciales de esta instalación. Comuníquese con SEO Group.'
}

export interface FieldHelp {
  key: string
  label: string
  help: string
}

/** Explicación de cada campo del heartbeat (lo que se manda cada pocos minutos). */
export const HEARTBEAT_FIELD_HELP: FieldHelp[] = [
  { key: 'sent_at', label: 'Fecha del envío', help: 'Cuándo se armó este mensaje.' },
  {
    key: 'fingerprint',
    label: 'Huella de la instalación',
    help: 'Identificador anónimo del equipo; no contiene datos personales.',
  },
  { key: 'version', label: 'Versión de SAVI', help: 'Qué versión del programa está instalada.' },
  {
    key: 'commit',
    label: 'Edición interna',
    help: 'Referencia interna de la versión, para dar soporte.',
  },
  {
    key: 'deployment_mode',
    label: 'Modo de instalación',
    help: 'Si SAVI corre como servidor o en un escritorio.',
  },
  { key: 'started_at', label: 'Último arranque', help: 'Cuándo se encendió SAVI por última vez.' },
  { key: 'tls', label: 'Conexión segura', help: 'Si el acceso web usa certificado.' },
  {
    key: 'llm',
    label: 'Proveedor de IA',
    help: 'Qué proveedor y modelo usa SAVI y si está listo. Nunca se envían las claves.',
  },
  {
    key: 'erp_databases',
    label: 'Bases del ERP',
    help: 'Cuántas bases hay configuradas y cuántas funcionan. Sin direcciones ni credenciales.',
  },
  {
    key: 'active_sessions',
    label: 'Sesiones activas',
    help: 'Cuántas personas tienen la sesión abierta, sin nombres.',
  },
  {
    key: 'sync',
    label: 'Estado del envío',
    help: 'Hasta dónde se enviaron los datos y el último error, si hubo.',
  },
  {
    key: 'warnings',
    label: 'Avisos',
    help: 'Problemas detectados en esta instalación, como códigos cortos.',
  },
]

/** Explicación de cada tipo de evento que viaja a SAVI Cloud. */
export const EVENT_STREAM_HELP: Record<string, string> = {
  turn: 'Cada respuesta de SAVI: proveedor, modelo, costo, herramientas usadas y tiempo. No incluye la pregunta ni la respuesta.',
  conversation: 'Cada conversación: fecha y base asociada. No incluye su contenido ni el título.',
  session: 'Cada inicio de sesión, con una referencia anónima de la persona.',
  free_query:
    'Cada consulta libre al ERP: resultado, cantidad de filas y duración. No incluye el SQL ni los datos.',
  database:
    'Las bases del ERP configuradas: código, nombre y si están en uso. Sin direcciones ni credenciales.',
}

export const NOT_SENT: string[] = [
  'Las preguntas que hacen las personas.',
  'Las respuestas de SAVI.',
  'Las consultas SQL.',
  'Los datos del ERP (clientes, facturas, saldos, etc.).',
  'Los nombres de usuario: las personas viajan con una referencia anónima.',
  'Contraseñas, claves de proveedores de IA ni credenciales de las bases.',
]
