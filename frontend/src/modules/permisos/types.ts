import type { AuthUser } from '@/modules/auth/types'

export interface BootstrapResponse {
  user: AuthUser
  modules: string[]
  version: string
}

export interface ModulesVersionResponse {
  version: string
}
