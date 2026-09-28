import { HttpClient } from '@/lib/HttpClient'
import type {
  CreateWebSourceRequest,
  PreviewWebSourceRequest,
  UpdateWebSourceRequest,
  WebSource,
  WebSourceDetail,
  WebSourcePreview,
} from '../types'

class WebSourceService {
  private readonly http = new HttpClient('/admin/company-web-sources')

  list(): Promise<WebSource[]> {
    return this.http.get<WebSource[]>('')
  }

  get(id: string): Promise<WebSourceDetail> {
    return this.http.get<WebSourceDetail>(`/${id}`)
  }

  /** Descubre las páginas y lee la primera, sin guardar nada. */
  preview(body: PreviewWebSourceRequest): Promise<WebSourcePreview> {
    return this.http.post<WebSourcePreview>('/preview', body)
  }

  create(body: CreateWebSourceRequest): Promise<WebSource> {
    return this.http.post<WebSource>('', body)
  }

  update(id: string, body: UpdateWebSourceRequest): Promise<WebSource> {
    return this.http.patch<WebSource>(`/${id}`, body)
  }

  refresh(id: string): Promise<WebSource> {
    return this.http.post<WebSource>(`/${id}/refresh`)
  }

  remove(id: string): Promise<void> {
    return this.http.delete<void>(`/${id}`)
  }
}

export const webSourceService = new WebSourceService()
