/**
 * Cliente HTTP de la consola.
 *
 * El access token vive solo en memoria (nunca en localStorage) y el refresh viaja en una
 * cookie HttpOnly que el navegador adjunta solo. Ante un 401 se renueva la sesión una vez y
 * se reintenta; si no se puede, se avisa para volver al login.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryAfter: number | null

  constructor(status: number, code: string, message: string, retryAfter: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}

export interface SessionBridge {
  getAccessToken(): string | null
  /** Renueva la sesión con la cookie de refresh; devuelve el token nuevo o `null` si venció. */
  refresh(): Promise<string | null>
  onSessionLost(): void
}

let bridge: SessionBridge | null = null

export function configureHttp(next: SessionBridge | null): void {
  bridge = next
}

type Query = Record<string, string | number | boolean | null | undefined>

export interface RequestOptions {
  body?: unknown
  query?: Query
  /** `false` en las rutas de autenticación (no llevan Bearer ni intentan renovar). */
  auth?: boolean
}

function buildUrl(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `${path}?${text}` : path
}

async function parseError(response: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `Error ${response.status}`
  try {
    const data = (await response.json()) as { errorCode?: string; message?: string }
    code = data.errorCode ?? code
    message = data.message ?? message
  } catch {
    // Cuerpo vacío o no JSON: se queda con el estado.
  }
  const retry = response.headers.get('Retry-After')
  return new ApiError(response.status, code, message, retry ? Number(retry) : null)
}

async function send(method: string, path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.auth !== false) {
    const token = bridge?.getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  return fetch(buildUrl(path, options.query), {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    credentials: 'same-origin',
  })
}

export async function request<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let response = await send(method, path, options)

  if (response.status === 401 && options.auth !== false && bridge) {
    const token = await bridge.refresh()
    if (token) {
      response = await send(method, path, options)
    } else {
      bridge.onSessionLost()
    }
  }
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const http = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
