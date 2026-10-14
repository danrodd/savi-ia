/** Tipos del API de la consola (reflejan `cloud/backend`; se escriben a mano). */

export type Role = 'admin' | 'soporte' | 'comercial'

export type Permission =
  | 'overview.read'
  | 'clients.read'
  | 'clients.write'
  | 'clients.suspend'
  | 'clients.policy'
  | 'instances.read'
  | 'instances.read_technical'
  | 'instances.manage'
  | 'tokens.manage'
  | 'alerts.read'
  | 'alerts.manage'
  | 'alerts.configure'
  | 'staff.manage'
  | 'audit.read'

export interface StaffUser {
  id: string
  email: string
  full_name: string
  role: Role
  permissions: Permission[]
}

export interface TokenResponse {
  access_token: string
  expires_in: number
  must_change_password: boolean
  user: StaffUser
}

export interface LoginStep {
  status: 'mfa_required' | 'mfa_setup_required'
  token: string
  must_change_password: boolean
}

export interface MfaSetup {
  secret: string
  otpauth_uri: string
}

export interface Client {
  id: string
  code: string
  name: string
  nit: string | null
  status: 'active' | 'suspended'
  created_at: string
  updated_at: string
  instances_total: number
  instances_online: number
  last_seen_at: string | null
  oldest_version: string | null
  /** `named`: las personas se identifican por su código de usuario (organización interna). */
  identity_mode: 'pseudonym' | 'named'
  /** Las instalaciones del cliente quedan solo con el chat. */
  config_locked: boolean
  /** La instalación local puede ofrecer el CLI de Claude con la cuenta de la persona. */
  allow_local_cli: boolean
  ai_policy: AiPolicy
  access_policy: AccessPolicy
}

export interface Page<T> {
  items: T[]
  total: number
}

export interface Instance {
  id: string
  client_id: string
  client_code: string
  client_name: string
  name: string
  deployment_mode: string
  os: string
  agent_db_engine: string
  version: string | null
  commit: string | null
  status: 'active' | 'suspended' | 'revoked'
  online: boolean
  outdated: boolean
  enrolled_at: string
  last_seen_at: string | null
  status_reason: string | null
  fingerprint: string | null
  clock_skew_seconds: number | null
  rotation_requested_at: string | null
  last_heartbeat: Record<string, unknown> | null
}

export interface Heartbeat {
  id: string
  received_at: string
  payload: Record<string, unknown>
}

export interface Cursored<T> {
  items: T[]
  next_cursor: string | null
}

export interface EnrollmentToken {
  id: string
  state: 'pending' | 'used' | 'expired' | 'revoked'
  expires_at: string
  created_at: string
  created_by: string
  used_at: string | null
  used_by_instance_id: string | null
  revoked_at: string | null
}

export interface CreatedToken {
  id: string
  token: string
  expires_at: string
}

export interface StaffMember {
  id: string
  email: string
  full_name: string
  role: Role
  is_active: boolean
  mfa_enabled: boolean
  last_login_at: string | null
  created_at: string
}

export interface CreatedStaff extends StaffMember {
  temporary_password: string
}

export interface AuditEntry {
  id: string
  occurred_at: string
  actor_email: string | null
  action: string
  target_type: string | null
  target_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  ip: string | null
}

export type Severity = 'info' | 'warning' | 'critical'

export interface Alert {
  id: string
  rule_code: string
  severity: Severity
  status: 'open' | 'acknowledged' | 'resolved'
  client_id: string
  instance_id: string | null
  details: Record<string, unknown>
  opened_at: string
  acknowledged_at: string | null
  acknowledged_by: string | null
  resolved_at: string | null
  resolved_by: string | null
  resolution_note: string | null
}

export interface AlertRule {
  code: string
  title: string
  description: string
  enabled: boolean
  severity: Severity
  threshold: number | null
  threshold_unit: string | null
  default_threshold: number | null
  auto_resolve: boolean
}

export interface Usage {
  turns: number
  conversations: number
  active_users: number
  entering_users: number
  adoption: number | null
  tokens: number
  cost_usd: string
  cost_per_active_user: string | null
  turns_without_price: number
  turns_with_error: number
  turns_interrupted: number
  turns_truncated: number
  error_rate: number | null
  latency_p50_ms: number | null
  latency_p90_ms: number | null
  free_queries: number
  free_queries_failed: number
}

export interface DayPoint {
  day: string
  turns: number
  active_users: number
  tokens: number
  cost_usd: string
  turns_with_error: number
  latency_p50_ms: number | null
  latency_p90_ms: number | null
}

export interface ModelUsage {
  provider: string | null
  model: string | null
  turns: number
  tokens: number
  cost_usd: string
}

export interface Freshness {
  seconds: number | null
  last_seen_at: string | null
}

export interface ClientMetrics {
  period: { start: string; end: string }
  freshness: Freshness
  totals: Usage
  series: DayPoint[]
  by_model: ModelUsage[]
  by_database: {
    database_ref: string | null
    name: string | null
    turns: number
    tokens: number
    cost_usd: string
  }[]
  tools: { name: string; tipo: string | null; uses: number; errors: number }[]
  finish_reasons: Record<string, number>
}

export interface Overview {
  clients: { active: number; suspended: number }
  instances: { online: number; offline: number; suspended: number; revoked: number }
  period: { start: string; end: string }
  freshness: Freshness
  usage: Usage
  trend: DayPoint[]
  providers: ModelUsage[]
  versions: { version: string | null; instances: number }[]
  open_alerts: Record<Severity, number>
}

export interface ClientDatabase {
  database_ref: string
  code: string
  name: string
  is_active: boolean
  is_usable: boolean
  credentials_unreadable: boolean
  last_connection_ok_at: string | null
  snapshot_date: string
}

/** Bases (`database_ref`) que puede consultar cada persona; solo restringe lo que da el ERP. */
/** Grupo con nombre: personas que comparten las mismas bases. */
export interface AccessGroup {
  /** `null` al crear: Cloud le asigna uno. */
  id: string | null
  name: string
  members: string[]
  databases: string[]
  /** Tope mensual de IA (USD) por miembro; `null` = el grupo no fija tope. */
  user_monthly_usd: string | null
}

export interface AccessPolicy {
  /** `null` = sin restricción general (manda el ERP). */
  default_databases: string[] | null
  /** Regla propia por `user_ref`; una lista vacía deja a la persona sin ninguna base. */
  user_databases: Record<string, string[]>
  /** Se compilan a reglas por persona al bajar a las instalaciones. */
  groups: AccessGroup[]
}

/** Proveedores y topes de IA de un cliente (montos en USD como texto). */
export interface AiPolicy {
  /** `null` = todos los proveedores. */
  allowed_providers: string[] | null
  user_monthly_usd: string | null
  provider_monthly_usd: Record<string, string>
  user_overrides: Record<string, string>
}

/** Plan del cliente y estado de su vigencia (montos en USD como texto). */
export interface Subscription {
  plan_name: string | null
  monthly_fee_usd: string | null
  max_users: number | null
  /** Último día cubierto (`AAAA-MM-DD`). */
  valid_until: string | null
  notes: string | null
  status: 'none' | 'active' | 'expiring' | 'expired'
  days_left: number | null
}

export type SubscriptionInput = Pick<
  Subscription,
  'plan_name' | 'monthly_fee_usd' | 'max_users' | 'valid_until' | 'notes'
>

/** Pago o ajuste que registró el staff. */
export interface LedgerEntry {
  id: string
  kind: 'payment' | 'adjustment'
  amount_usd: string
  note: string
  extends_until: string | null
  created_by: string
  created_at: string
}

export interface LedgerEntryInput {
  kind: 'payment' | 'adjustment'
  amount_usd: string
  note: string
  extends_until: string | null
}

export interface Person {
  user_ref: string
  /** Solo en clientes con identidad `named`. */
  label: string | null
  sessions: number
  last_session_at: string
}

export interface ClientUser {
  user_ref: string
  label: string | null
  turns: number
  cost_usd: string
  last_used_at: string
  databases_used: number
}

export interface MetricDefinition {
  key: string
  label: string
  definition: string
  source: string
}
