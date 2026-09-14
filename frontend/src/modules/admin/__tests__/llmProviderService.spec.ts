import { afterEach, describe, expect, it, vi } from 'vitest'
import { installAuthBridge } from '@/lib/authBridge'
import { llmProviderService } from '../services/llmProviderService'

describe('llmProviderService', () => {
  installAuthBridge({
    getAccessToken: () => null,
    refreshAccessToken: async () => '',
    clearSession: () => undefined,
    redirectToLogin: () => undefined,
    reloadPermisos: () => undefined,
  })

  afterEach(() => vi.restoreAllMocks())

  it('saves through the provider PUT endpoint without transforming the credential', async () => {
    const response = { provider: 'gemini' }
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }))

    await llmProviderService.save('gemini', {
      credential_kind: 'api_key',
      credential: 'temporary-secret',
      chat_model: 'gemini-2.5-flash',
      title_model: 'gemini-2.5-flash',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/admin/llm-providers/gemini'),
      expect.objectContaining({ method: 'PUT', body: expect.stringContaining('temporary-secret') }),
    )
  })
})
