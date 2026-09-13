import { HttpClient } from '@/lib/HttpClient'
import type {
  AvailableErpDatabase,
  ConnectionTestResult,
  ErpDatabase,
  ExportedErpDatabasesFile,
  ImportErpDatabasesResult,
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

  /** El `payload` viaja cifrado con `passphrase` — el backend no ve la contraseña de las bases. */
  export(passphrase: string): Promise<ExportedErpDatabasesFile> {
    return this.admin.post<ExportedErpDatabasesFile>('/export', { passphrase })
  }

  /** Por `code`: crea las que no existen en esta instalación y actualiza las que sí. */
  import(passphrase: string, payload: string): Promise<ImportErpDatabasesResult> {
    return this.admin.post<ImportErpDatabasesResult>('/import', { passphrase, payload })
  }
}

export const erpDatabaseService = new ErpDatabaseService()
