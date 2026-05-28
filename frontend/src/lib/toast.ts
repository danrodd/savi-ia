import { toast as sonner } from 'vue-sonner'

interface ToastOptions {
  description?: string
  duration?: number
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
  promise<T>(promise: Promise<T>, messages: { loading: string; success: string; error: string }) {
    return sonner.promise(promise, messages)
  },
}
