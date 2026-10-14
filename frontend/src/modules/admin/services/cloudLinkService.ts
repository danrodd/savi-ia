import { HttpClient } from '@/lib/HttpClient'
import type { CloudHistoryMode, CloudLinkState, CloudPreview } from '../types'

class CloudLinkService {
  private readonly http = new HttpClient('/admin/cloud-link')

  status(): Promise<CloudLinkState> {
    return this.http.get<CloudLinkState>('')
  }

  link(token: string, history: CloudHistoryMode): Promise<CloudLinkState> {
    return this.http.post<CloudLinkState, { token: string; history: CloudHistoryMode }>('', {
      token,
      history,
    })
  }

  unlink(): Promise<void> {
    return this.http.delete<void>('')
  }

  syncNow(): Promise<{ accepted: boolean }> {
    return this.http.post<{ accepted: boolean }>('/sync-now')
  }

  preview(): Promise<CloudPreview> {
    return this.http.get<CloudPreview>('/preview')
  }
}

export const cloudLinkService = new CloudLinkService()
