/**
 * Servicio del subsistema de permisos.
 *
 * Usa el HttpClient global porque el Bearer y el refresh-on-401 ya están
 * resueltos ahí. A diferencia de `authService` (que usa fetch directo
 * para evitar ciclos), permisos sí depende de tener un access token
 * válido — el bootstrap se llama solo cuando hay sesión, post-login.
 */
import { HttpClient } from '@/lib/HttpClient'
import type { BootstrapResponse, ModulesVersionResponse } from '../types'

const http = new HttpClient('/auth')

class PermisosService {
  async getBootstrap(): Promise<BootstrapResponse> {
    return http.get<BootstrapResponse>('/me/bootstrap')
  }

  async getVersion(): Promise<ModulesVersionResponse> {
    return http.get<ModulesVersionResponse>('/me/modules-version')
  }
}

export const permisosService = new PermisosService()
