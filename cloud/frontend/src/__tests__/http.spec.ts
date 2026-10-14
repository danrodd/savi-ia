import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, configureHttp, http, request } from '@/lib/http'

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

describe('http', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    configureHttp(null)
    vi.unstubAllGlobals()
  })

  it('adjunta el Bearer y arma la query sin valores vacíos', async () => {
    configureHttp({
      getAccessToken: () => 'tok',
      refresh: async () => null,
      onSessionLost: () => undefined,
    })
    fetchMock.mockResolvedValue(json({ ok: true }))

    await http.get('/console/api/clients', { q: 'abc', status: '', limit: 10 })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/console/api/clients?q=abc&limit=10')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })

  it('renueva la sesión una vez ante un 401 y reintenta con el token nuevo', async () => {
    let token = 'viejo'
    const refresh = vi.fn(async () => {
      token = 'nuevo'
      return token
    })
    configureHttp({ getAccessToken: () => token, refresh, onSessionLost: vi.fn() })
    fetchMock
      .mockResolvedValueOnce(json({ errorCode: 'unauthorized', message: 'x' }, 401))
      .mockResolvedValueOnce(json({ value: 1 }))

    const result = await http.get<{ value: number }>('/console/api/overview')

    expect(result.value).toBe(1)
    expect(refresh).toHaveBeenCalledTimes(1)
    const retry = fetchMock.mock.calls[1] as [string, RequestInit]
    expect((retry[1].headers as Record<string, string>).Authorization).toBe('Bearer nuevo')
  })

  it('avisa que se perdió la sesión si no se puede renovar', async () => {
    const onSessionLost = vi.fn()
    configureHttp({ getAccessToken: () => 'tok', refresh: async () => null, onSessionLost })
    fetchMock.mockResolvedValue(json({ errorCode: 'unauthorized', message: 'Iniciá sesión' }, 401))

    await expect(http.get('/console/api/overview')).rejects.toMatchObject({
      status: 401,
      code: 'unauthorized',
    })
    expect(onSessionLost).toHaveBeenCalledTimes(1)
  })

  it('no intenta renovar ni manda Bearer en las rutas de autenticación', async () => {
    const refresh = vi.fn(async () => 'x')
    configureHttp({ getAccessToken: () => 'tok', refresh, onSessionLost: vi.fn() })
    fetchMock.mockResolvedValue(json({ errorCode: 'invalid_credentials', message: 'No' }, 401))

    await expect(
      request('POST', '/console/auth/login', { body: { email: 'a', password: 'b' }, auth: false }),
    ).rejects.toMatchObject({ code: 'invalid_credentials' })

    expect(refresh).not.toHaveBeenCalled()
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined()
  })

  it('conserva el errorCode, el mensaje y Retry-After del backend', async () => {
    fetchMock.mockResolvedValue(
      json({ errorCode: 'too_many_requests', message: 'Esperá' }, 429, { 'Retry-After': '30' }),
    )
    const error = await http.post('/console/api/clients', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 429, code: 'too_many_requests', retryAfter: 30 })
  })

  it('devuelve undefined en un 204', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    expect(await http.delete('/console/api/enrollment-tokens/1')).toBeUndefined()
  })
})
