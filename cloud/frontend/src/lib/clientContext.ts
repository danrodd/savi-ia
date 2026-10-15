import { type ComputedRef, type InjectionKey, inject, type Ref } from 'vue'
import type { Client } from '@/lib/types'

/**
 * Lo que el detalle del cliente comparte con sus pestañas: el cliente ya cargado (una sola
 * petición para todas) y cómo recargarlo después de guardar algo.
 */
export interface ClientContext {
  id: ComputedRef<string>
  client: Ref<Client | null>
  reload: () => Promise<void>
}

export const CLIENT_CONTEXT: InjectionKey<ClientContext> = Symbol('client-context')

export function useClientContext(): ClientContext {
  const context = inject(CLIENT_CONTEXT)
  if (!context) throw new Error('Esta pestaña solo existe dentro del detalle de un cliente.')
  return context
}
