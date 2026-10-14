import { HttpClient } from '@/lib/HttpClient'

class MfaAdminService {
  private readonly http = new HttpClient('/admin/mfa')

  /** `reset: false` = la persona no tenía segundo factor (no es un error). */
  reset(login: string): Promise<{ reset: boolean }> {
    return this.http.post<{ reset: boolean }, { login: string }>('/reset', { login })
  }
}

export const mfaAdminService = new MfaAdminService()
