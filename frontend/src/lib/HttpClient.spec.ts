import { afterEach, describe, expect, it, vi } from 'vitest'
import { installAuthBridge } from './authBridge'
import { HttpClient } from './HttpClient'

describe('HttpClient query serialization', () => {
  installAuthBridge({
    getAccessToken: () => null,
    refreshAccessToken: async () => '',
    clearSession: () => undefined,
    redirectToLogin: () => undefined,
    reloadPermisos: () => undefined,
  })

  afterEach(() => vi.restoreAllMocks())

  it('serializes a string[] query value as a repeated param', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }))

    const client = new HttpClient('/usage')
    await client.get('/system', { query: { provider: ['claude', 'gemini'] } })

    const url = new URL(fetchMock.mock.calls[0]?.[0] as string)
    expect(url.searchParams.getAll('provider')).toEqual(['claude', 'gemini'])
  })

  it('omits the param entirely for an empty array', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }))

    const client = new HttpClient('/usage')
    await client.get('/system', { query: { provider: [] } })

    const url = new URL(fetchMock.mock.calls[0]?.[0] as string)
    expect(url.searchParams.has('provider')).toBe(false)
  })

  it('still serializes scalar values as a single param', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }))

    const client = new HttpClient('/usage')
    await client.get('/system', { query: { from: '2026-09-21', limit: 10 } })

    const url = new URL(fetchMock.mock.calls[0]?.[0] as string)
    expect(url.searchParams.get('from')).toBe('2026-09-21')
    expect(url.searchParams.get('limit')).toBe('10')
  })
})
