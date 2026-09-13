import { HttpClient } from '@/lib/HttpClient'
import type {
  AvailableErpDatabase,
  ConnectionTestResult,
  ErpDatabase,
  SaveErpDatabaseRequest,
} from '../types'

class ErpDatabaseService {
  private readonly admin = new HttpClient('/admin/erp-databases')
  private readonly publicHttp = new HttpClient('/erp-databases')

  list(includeInactive = true): Promise<ErpDatabase[]> {
    return this.admin.get<ErpDatabase[]>('', { query: { include_inactive: includeInactive } })
  }

  get(id: string): Promise<ErpDatabase> {
    return this.admin.get<ErpDatabase>(`/${id}`)
  }

  create(body: SaveErpDatabaseRequest): Promise<ErpDatabase> {
    return this.admin.post<ErpDatabase>('', body)
  }

  update(id: string, body: SaveErpDatabaseRequest): Promise<ErpDatabase> {
    return this.admin.patch<ErpDatabase>(`/${id}`, body)
  }

  /** Con `databaseId` reutiliza la contraseña guardada si no se envía una. */
  testConnection(body: SaveErpDatabaseRequest, databaseId?: string): Promise<ConnectionTestResult> {
    return this.admin.post<ConnectionTestResult>('/test-connection', body, {
      query: { database_id: databaseId },
    })
  }

  setDefault(id: string): Promise<ErpDatabase> {
    return this.admin.post<ErpDatabase>(`/${id}/set-default`)
  }

  activate(id: string): Promise<ErpDatabase> {
    return this.admin.post<ErpDatabase>(`/${id}/activate`)
  }

  deactivate(id: string): Promise<ErpDatabase> {
    return this.admin.post<ErpDatabase>(`/${id}/deactivate`)
  }

  remove(id: string): Promise<void> {
    return this.admin.delete<void>(`/${id}`)
  }

  /** Bases a las que el usuario autenticado tiene acceso. Cualquier usuario. */
  available(): Promise<AvailableErpDatabase[]> {
    return this.publicHttp.get<AvailableErpDatabase[]>('/available')
  }
}

export const erpDatabaseService = new ErpDatabaseService()
