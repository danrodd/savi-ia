import { HttpClient } from '@/lib/HttpClient'
import type {
  CompanyDocument,
  CompanyDocumentUsage,
  DocumentPermissions,
  SearchTestResult,
  UpdateCompanyDocumentRequest,
} from '../types'

class CompanyDocumentService {
  private readonly http = new HttpClient('/admin/company-documents')

  list(): Promise<CompanyDocument[]> {
    return this.http.get<CompanyDocument[]>('', { query: { limit: 200 } })
  }

  usage(): Promise<CompanyDocumentUsage> {
    return this.http.get<CompanyDocumentUsage>('/usage')
  }

  /** El backend detecta el tipo por contenido; la extensión no decide nada. */
  upload(file: File, title: string, permissions: DocumentPermissions): Promise<CompanyDocument> {
    const form = new FormData()
    form.append('file', file)
    form.append('visibility', permissions.visibility)
    form.append('all_databases', String(permissions.all_databases))
    if (title.trim()) form.append('title', title.trim())
    for (const module of permissions.modules) form.append('modules', module)
    for (const id of permissions.database_ids) form.append('database_ids', id)
    return this.http.postForm<CompanyDocument>('', form)
  }

  update(id: string, body: UpdateCompanyDocumentRequest): Promise<CompanyDocument> {
    return this.http.patch<CompanyDocument>(`/${id}`, body)
  }

  replace(id: string, file: File): Promise<CompanyDocument> {
    const form = new FormData()
    form.append('file', file)
    return this.http.postForm<CompanyDocument>(`/${id}/replace`, form)
  }

  reprocess(id: string): Promise<CompanyDocument> {
    return this.http.post<CompanyDocument>(`/${id}/reprocess`)
  }

  remove(id: string): Promise<void> {
    return this.http.delete<void>(`/${id}`)
  }

  searchTest(query: string, erpDatabaseId: string, asLogin?: string): Promise<SearchTestResult> {
    return this.http.post<SearchTestResult>('/search-test', {
      query,
      erp_database_id: erpDatabaseId,
      as_login: asLogin?.trim() || undefined,
    })
  }
}

export const companyDocumentService = new CompanyDocumentService()
