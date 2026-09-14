import { HttpClient } from '@/lib/HttpClient'
import type {
  LlmProvider,
  LlmProviderKind,
  ProviderModel,
  ProviderTestResponse,
  SaveLlmProviderRequest,
} from '../types'

class LlmProviderService {
  private readonly http = new HttpClient('/admin/llm-providers')

  list(): Promise<LlmProvider[]> {
    return this.http.get<LlmProvider[]>('')
  }

  save(provider: LlmProviderKind, body: SaveLlmProviderRequest): Promise<LlmProvider> {
    return this.http.put<LlmProvider>(`/${provider}`, body)
  }

  test(provider: LlmProviderKind, body: SaveLlmProviderRequest): Promise<ProviderTestResponse> {
    return this.http.post<ProviderTestResponse>(`/${provider}/test`, body)
  }

  models(provider: LlmProviderKind): Promise<{ models: ProviderModel[] }> {
    return this.http.get<{ models: ProviderModel[] }>(`/${provider}/models`)
  }

  activate(provider: LlmProviderKind): Promise<LlmProvider> {
    return this.http.post<LlmProvider>(`/${provider}/activate`)
  }
}

export const llmProviderService = new LlmProviderService()
