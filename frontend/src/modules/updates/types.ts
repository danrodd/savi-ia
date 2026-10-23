/** Contrato de `GET /updates/status` (spec 09, actualización automática). */
export type UpdateState = 'up_to_date' | 'recommended' | 'required' | 'blocked'

export type ApplyPhase = 'idle' | 'downloading' | 'waiting_turns' | 'installing' | 'failed'

/** Cómo terminó un intento de instalación, ya contrastado con la versión que corre. */
export type InstallOutcome =
  | 'installed'
  | 'rolled_back'
  | 'failed'
  | 'cancelled'
  | 'timeout'
  | 'interrupted'

/** Un intento de instalación ya resuelto. */
export interface InstallRecord {
  attempt_id: string
  from_version: string
  to_version: string
  outcome: InstallOutcome
  started_at: string
  finished_at: string
  exit_code: number | null
  /** Texto para la persona, ya en usted. */
  message: string
}

export interface UpdateStatus {
  /** `false` en desarrollo o sin servidor de actualizaciones: no se muestra nada. */
  enabled: boolean
  state: UpdateState
  current_version: string | null
  available_version: string | null
  notes: string | null
  published_at: string | null
  size: number | null
  /** Solo con `state = 'required'`: fecha límite antes del bloqueo. */
  deadline: string | null
  /** `false` si SAVI está en un servidor y este navegador es de otro equipo. */
  can_apply: boolean
  phase: ApplyPhase
  downloaded_bytes: number
  error: string | null
  checked_at: string | null
  /** El último intento de instalación, de esta sesión o de una anterior. */
  last_install: InstallRecord | null
}

/** Qué pinta la interfaz con el estado actual. */
export type UpdateNoticeKind = 'none' | 'banner' | 'blocked' | 'progress'

/** Aviso del resultado del último intento: se muestra una sola vez. */
export interface ResultNotice {
  tone: 'success' | 'warning'
  message: string
  attemptId: string
}
