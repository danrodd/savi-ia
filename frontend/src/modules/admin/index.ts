/**
 * Contrato público del módulo `admin`. Importa SIEMPRE desde
 * `@/modules/admin`, nunca desde subcarpetas internas.
 */

export { erpDatabaseService } from './services/erpDatabaseService'
export { useErpDatabaseStore } from './stores/erpDatabaseStore'
export type {
  AvailableErpDatabase,
  ConnectionTestResult,
  ErpDatabase,
  SaveErpDatabaseRequest,
} from './types'
