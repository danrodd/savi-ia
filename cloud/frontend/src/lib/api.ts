/** Llamadas al API de la consola (`/console/api`) y de autenticación (`/console/auth`). */

import { http, request } from './http'
import type {
  AccessPolicy,
  AiPolicy,
  Alert,
  AlertRule,
  AuditEntry,
  Client,
  ClientDatabase,
  ClientMetrics,
  ClientUser,
  CreatedStaff,
  CreatedToken,
  Cursored,
  EnrollmentToken,
  Heartbeat,
  Instance,
  LedgerEntry,
  LedgerEntryInput,
  LoginStep,
  MetricDefinition,
  MfaSetup,
  Overview,
  Page,
  Person,
  Role,
  Severity,
  StaffMember,
  Subscription,
  SubscriptionInput,
  TokenResponse,
} from './types'

const API = '/console/api'
const AUTH = '/console/auth'

export interface Period {
  start?: string
  end?: string
}

export const authApi = {
  login: (email: string, password: string) =>
    request<LoginStep>('POST', `${AUTH}/login`, { body: { email, password }, auth: false }),
  mfa: (mfaToken: string, code: string) =>
    request<TokenResponse>('POST', `${AUTH}/mfa`, {
      body: { mfa_token: mfaToken, code },
      auth: false,
    }),
  beginSetup: (setupToken: string) =>
    request<MfaSetup>('POST', `${AUTH}/mfa/setup`, {
      body: { setup_token: setupToken },
      auth: false,
    }),
  confirmSetup: (setupToken: string, code: string, newPassword: string | null) =>
    request<TokenResponse>('POST', `${AUTH}/mfa/setup/confirm`, {
      body: { setup_token: setupToken, code, new_password: newPassword },
      auth: false,
    }),
  refresh: () => request<TokenResponse>('POST', `${AUTH}/refresh`, { auth: false }),
  logout: () => request<void>('POST', `${AUTH}/logout`, { auth: false }),
}

export const consoleApi = {
  me: () => http.get<TokenResponse['user']>(`${API}/me`),
  overview: (period: Period = {}) => http.get<Overview>(`${API}/overview`, { ...period }),
  definitions: () => http.get<MetricDefinition[]>(`${API}/metric-definitions`),

  clients: (query: {
    q?: string
    status?: string
    sort?: string
    limit?: number
    offset?: number
  }) => http.get<Page<Client>>(`${API}/clients`, query),
  client: (id: string) => http.get<Client>(`${API}/clients/${id}`),
  createClient: (body: { code: string; name: string; nit?: string | null }) =>
    http.post<Client>(`${API}/clients`, body),
  updateClient: (id: string, body: { name?: string; nit?: string | null }) =>
    http.patch<Client>(`${API}/clients/${id}`, body),
  setClientPolicy: (
    id: string,
    body: {
      identity_mode?: 'pseudonym' | 'named'
      config_locked?: boolean
      allow_local_cli?: boolean
    },
  ) => http.patch<Client>(`${API}/clients/${id}/policy`, body),
  setClientAccessPolicy: (id: string, body: AccessPolicy) =>
    http.put<Client>(`${API}/clients/${id}/access-policy`, body),
  setClientAiPolicy: (id: string, body: AiPolicy) =>
    http.put<Client>(`${API}/clients/${id}/ai-policy`, body),
  subscription: (id: string) => http.get<Subscription>(`${API}/clients/${id}/subscription`),
  setSubscription: (id: string, body: SubscriptionInput) =>
    http.put<Subscription>(`${API}/clients/${id}/subscription`, body),
  ledger: (id: string) => http.get<LedgerEntry[]>(`${API}/clients/${id}/ledger`),
  recordLedgerEntry: (id: string, body: LedgerEntryInput) =>
    http.post<LedgerEntry>(`${API}/clients/${id}/ledger`, body),
  suspendClient: (id: string) => http.post<Client>(`${API}/clients/${id}/suspend`),
  activateClient: (id: string) => http.post<Client>(`${API}/clients/${id}/activate`),
  clientMetrics: (id: string, period: Period = {}) =>
    http.get<ClientMetrics>(`${API}/clients/${id}/metrics`, { ...period }),
  clientDatabases: (id: string) => http.get<ClientDatabase[]>(`${API}/clients/${id}/databases`),
  clientUsers: (id: string, period: Period = {}) =>
    http.get<ClientUser[]>(`${API}/clients/${id}/users`, { ...period }),

  instances: (query: {
    client_id?: string
    status?: string
    connectivity?: string
    outdated?: boolean
  }) => http.get<Instance[]>(`${API}/instances`, query),
  instance: (id: string) => http.get<Instance>(`${API}/instances/${id}`),
  instancePeople: (id: string) => http.get<Person[]>(`${API}/instances/${id}/people`),
  heartbeats: (id: string, cursor?: string) =>
    http.get<Cursored<Heartbeat>>(`${API}/instances/${id}/heartbeats`, { limit: 20, cursor }),
  instanceAction: (
    id: string,
    action: 'suspend' | 'activate' | 'confirm-fingerprint' | 'request-rotation',
  ) => http.post<Instance>(`${API}/instances/${id}/${action}`),
  revokeInstance: (id: string, confirm: string) =>
    http.post<Instance>(`${API}/instances/${id}/revoke`, { confirm }),

  tokens: (clientId: string) =>
    http.get<EnrollmentToken[]>(`${API}/clients/${clientId}/enrollment-tokens`),
  createToken: (clientId: string, expiresHours: number) =>
    http.post<CreatedToken>(`${API}/clients/${clientId}/enrollment-tokens`, {
      expires_hours: expiresHours,
    }),
  revokeToken: (tokenId: string) => http.delete<void>(`${API}/enrollment-tokens/${tokenId}`),

  alerts: (query: { status?: string; severity?: Severity; client_id?: string }) =>
    http.get<Alert[]>(`${API}/alerts`, query),
  acknowledgeAlert: (id: string) => http.post<Alert>(`${API}/alerts/${id}/ack`),
  resolveAlert: (id: string, note: string) =>
    http.post<Alert>(`${API}/alerts/${id}/resolve`, { note }),
  alertRules: () => http.get<AlertRule[]>(`${API}/alert-rules`),
  updateRule: (
    code: string,
    body: { enabled?: boolean; threshold?: number; severity?: Severity },
  ) => http.patch<AlertRule>(`${API}/alert-rules/${code}`, body),

  staff: () => http.get<StaffMember[]>(`${API}/staff`),
  createStaff: (body: { email: string; full_name: string; role: Role }) =>
    http.post<CreatedStaff>(`${API}/staff`, body),
  updateStaff: (id: string, body: { full_name?: string; role?: Role }) =>
    http.patch<StaffMember>(`${API}/staff/${id}`, body),
  staffAction: (id: string, action: 'deactivate' | 'activate' | 'reset-mfa') =>
    http.post<StaffMember>(`${API}/staff/${id}/${action}`),

  audit: (query: { actor?: string; action?: string; cursor?: string }) =>
    http.get<Cursored<AuditEntry>>(`${API}/audit`, { limit: 50, ...query }),
}
