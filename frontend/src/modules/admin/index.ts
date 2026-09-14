/**
 * Contrato público del módulo `admin`. Importa SIEMPRE desde
 * `@/modules/admin`, nunca desde subcarpetas internas.
 */

export { erpDatabaseService } from './services/erpDatabaseService'
export { llmProviderService } from './services/llmProviderService'
export { useErpDatabaseStore } from './stores/erpDatabaseStore'
export { useLlmProviderStore } from './stores/llmProviderStore'
export type {
  AvailableErpDatabase,
  ConnectionTestResult,
  ErpDatabase,
  LlmCredentialKind,
  LlmProvider,
  LlmProviderKind,
  ModelPricing,
  ProviderModel,
  ProviderTestResponse,
  SaveErpDatabaseRequest,
  SaveLlmProviderRequest,
} from './types'
