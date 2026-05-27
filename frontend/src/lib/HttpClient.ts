import { ENV } from './env'

export interface RequestOptions {
  query?: Record<string, string | number | boolean | null | undefined>
  headers?: Record<string, string>
  signal?: AbortSignal
}

interface ReqOptionsWithBody extends RequestOptions {
  body?: unknown
}

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string; message?: string }
    return data.detail ?? data.message ?? `HTTP ${res.status} ${res.statusText}`
  } catch {
    return `HTTP ${res.status} ${res.statusText}`
  }
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

  private async request<T>(
    method: string,
    endpoint: string,
    opts: ReqOptionsWithBody = {},
  ): Promise<T> {
    const headers: Record<string, string> = {
      ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(opts.headers ?? {}),
    }
    const res = await fetch(this.buildUrl(endpoint, opts.query), {
      method,
      headers,
      signal: opts.signal,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
    if (!res.ok) throw new Error(await extractErrorMessage(res))
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

  delete<T>(endpoint: string, opts?: RequestOptions): Promise<T> {
    return this.request<T>('DELETE', endpoint, opts)
  }

  raw(
    endpoint: string,
    init: RequestInit & { query?: RequestOptions['query'] } = {},
  ): Promise<Response> {
    const { query, ...rest } = init
    return fetch(this.buildUrl(endpoint, query), rest)
  }
}
