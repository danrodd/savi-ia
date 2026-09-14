/**
 * HttpClient — wrapper sobre fetch con auth automática.
 *
 * Pipeline de cada request:
 *  1. Inyecta el header `Authorization: Bearer <access>` si hay sesión.
 *  2. Envía la request.
 *  3. Si la respuesta es 401:
 *      a. dispara (o se engancha a) un único refresh global (cola),
 *      b. reintenta la request original UNA vez con el nuevo access,
 *      c. si el refresh falla → limpia sesión + redirige a `/login`.
 *  4. Cualquier otra respuesta !ok se convierte en `Error` con `detail`.
 *
 * NO importa el store de Pinia directamente — usa `authBridge` para no
 * generar ciclos.
 */
import { getAuthBridge } from './authBridge'
import { ENV } from './env'

interface ValidationIssue {
  msg?: string
}

interface ErrorBody {
  // FastAPI devuelve un arreglo de issues cuando falla la validación del body (422).
  detail?: string | ValidationIssue[]
  message?: string
  errorCode?: string
  required_module?: string
}

/**
 * Error tipado para respuestas no-OK del backend. Lleva el status code
 * y el body parseado para que el caller pueda discriminar (ej. UI que
 * quiere mostrar el `required_module` de un 403).
 */
export class HttpRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: ErrorBody = {},
  ) {
    super(message)
    this.name = 'HttpRequestError'
  }
}

export interface RequestOptions {
  query?: Record<string, string | number | boolean | null | undefined>
  headers?: Record<string, string>
  signal?: AbortSignal
}

interface ReqOptionsWithBody extends RequestOptions {
  body?: unknown
}

async function readErrorBody(res: Response): Promise<ErrorBody> {
  try {
    return (await res.json()) as ErrorBody
  } catch {
    return {}
  }
}

function errorMessage(body: ErrorBody, res: Response): string {
  if (Array.isArray(body.detail)) {
    const messages = body.detail.map((issue) => issue.msg).filter(Boolean)
    if (messages.length > 0) return messages.join(' · ')
  } else if (body.detail) {
    return body.detail
  }
  return body.message ?? `HTTP ${res.status} ${res.statusText}`
}

function buildHeaders(
  body: unknown,
  custom: Record<string, string> | undefined,
  token: string | null,
): Record<string, string> {
  const headers: Record<string, string> = {
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(custom ?? {}),
  }
  if (token && !('Authorization' in headers)) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

export class HttpClient {
  constructor(private readonly resourcePath: string = '') {}

  private buildUrl(endpoint: string, query?: RequestOptions['query']): string {
    const base = ENV.API_BASE_URL.replace(/\/+$/, '')
    const resource = this.resourcePath.replace(/\/+$/, '')
    const ep = endpoint === '' ? '' : endpoint.startsWith('/') ? endpoint : `/${endpoint}`
    let url = `${base}${resource}${ep}`
    if (query) {
      const params = new URLSearchParams()
      for (const [k, v] of Object.entries(query)) {
        if (v === undefined || v === null) continue
        params.set(k, String(v))
      }
      const qs = params.toString()
      if (qs) url += `?${qs}`
    }
    return url
  }

  private async fetchWithAuth(
    url: string,
    init: RequestInit,
    customHeaders: Record<string, string> | undefined,
    body: unknown,
  ): Promise<Response> {
    const bridge = getAuthBridge()
    const token = bridge.getAccessToken()
    const initialHeaders = buildHeaders(body, customHeaders, token)
    let res = await fetch(url, { ...init, headers: initialHeaders })

    if (res.status !== 401) return res

    // 401: si no hay refresh disponible, no se intenta — el caller
    // recibe el error y el router lo redirige al login.
    try {
      const newToken = await bridge.refreshAccessToken()
      const retryHeaders = buildHeaders(body, customHeaders, newToken)
      res = await fetch(url, { ...init, headers: retryHeaders })
      if (res.status === 401) {
        bridge.clearSession()
        bridge.redirectToLogin(window.location.pathname + window.location.search)
      }
      return res
    } catch {
      // refresh falló (token revocado, expirado, sin refresh, etc.)
      bridge.clearSession()
      bridge.redirectToLogin(window.location.pathname + window.location.search)
      return res
    }
  }

  private async request<T>(
    method: string,
    endpoint: string,
    opts: ReqOptionsWithBody = {},
  ): Promise<T> {
    const url = this.buildUrl(endpoint, opts.query)
    const body = opts.body !== undefined ? JSON.stringify(opts.body) : undefined
    const res = await this.fetchWithAuth(
      url,
      { method, signal: opts.signal, body },
      opts.headers,
      opts.body,
    )
    if (!res.ok) {
      const errBody = await readErrorBody(res)
      // 403 con errorCode module_access_denied → la caché del set de
      // módulos quedó stale. Disparamos reload en background y propagamos
      // el error igual: la operación actual falla, pero la próxima ya
      // trabajará con el set fresco.
      if (res.status === 403 && errBody.errorCode === 'module_access_denied') {
        getAuthBridge().reloadPermisos()
      }
      throw new HttpRequestError(errorMessage(errBody, res), res.status, errBody)
    }
    if (res.status === 204) return undefined as T
    return (await res.json()) as T
  }

  get<T>(endpoint: string, opts?: RequestOptions): Promise<T> {
    return this.request<T>('GET', endpoint, opts)
  }

  post<T, B = unknown>(endpoint: string, body?: B, opts?: RequestOptions): Promise<T> {
    return this.request<T>('POST', endpoint, { ...opts, body })
  }

  patch<T, B = unknown>(endpoint: string, body?: B, opts?: RequestOptions): Promise<T> {
    return this.request<T>('PATCH', endpoint, { ...opts, body })
  }

  put<T, B = unknown>(endpoint: string, body?: B, opts?: RequestOptions): Promise<T> {
    return this.request<T>('PUT', endpoint, { ...opts, body })
  }

  delete<T>(endpoint: string, opts?: RequestOptions): Promise<T> {
    return this.request<T>('DELETE', endpoint, opts)
  }

  /**
   * Para SSE: devuelve la Response directa con auth inyectada y refresh
   * automático en caso de 401. El caller la procesa con readSseJson o
   * similar. NO se reintenta automáticamente si el chat ya empezó a
   * streamear y la sesión expira mid-stream — el handler de la consola
   * lo verá como una conexión cortada.
   */
  raw(
    endpoint: string,
    init: RequestInit & { query?: RequestOptions['query']; body?: BodyInit | null } = {},
  ): Promise<Response> {
    const { query, body, ...rest } = init
    const url = this.buildUrl(endpoint, query)
    // Para SSE el body ya viene como BodyInit (string). Tratamos `body`
    // como JSON solo cuando es string (caso común del chat).
    return this.fetchWithAuth(
      url,
      { ...rest, body },
      rest.headers as Record<string, string> | undefined,
      body,
    )
  }
}
