/**
 * API pública del módulo `permisos`.
 *
 * Regla: cualquier consumo de permisos en otro módulo importa SOLO
 * desde acá. Nunca tocar `stores/`, `composables/`, `services/`
 * directamente. Eso protege la API y evita acoplamiento.
 */
export { M, MODULE_LABELS, type ModuleCode } from './constants'
export { usePermisosStore } from './stores/permisosStore'
export { useModule } from './composables/useModule'
export { usePermisosPolling } from './composables/usePermisosPolling'
export { vModule } from './directives/vModule'
export { permisosService } from './services/permisosService'
export type { BootstrapResponse, ModulesVersionResponse } from './types'
