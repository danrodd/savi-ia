import { toast as sonner } from 'vue-sonner'

interface ToastOptions {
  description?: string
  /** Milisegundos; `Infinity` deja el aviso hasta que la persona lo cierre. */
  duration?: number
  /** Un botón dentro del aviso, por ejemplo "Ver". */
  action?: { label: string; onClick: () => void }
}

/**
 * Helper centralizado de toasts. Envuelve vue-sonner para que el resto del
 * código no dependa directamente de la librería y para mantener un API
 * consistente.
 */
export const toast = {
  success(message: string, options?: ToastOptions) {
    return sonner.success(message, options)
  },
  error(message: string, options?: ToastOptions) {
    return sonner.error(message, options)
  },
  info(message: string, options?: ToastOptions) {
    return sonner(message, options)
  },
  warning(message: string, options?: ToastOptions) {
    return sonner.warning(message, options)
  },
  promise<T>(promise: Promise<T>, messages: { loading: string; success: string; error: string }) {
    return sonner.promise(promise, messages)
  },
}
