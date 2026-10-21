/** Contrato de `GET /updates/status` (spec 09, actualización automática). */
export type UpdateState = 'up_to_date' | 'recommended' | 'required' | 'blocked'

export type ApplyPhase = 'idle' | 'downloading' | 'waiting_turns' | 'installing' | 'failed'

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
}

/** Qué pinta la interfaz con el estado actual. */
export type UpdateNoticeKind = 'none' | 'banner' | 'blocked' | 'progress'
