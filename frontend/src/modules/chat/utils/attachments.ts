import { HttpRequestError } from '@/lib/HttpClient'

/** Espejo de los límites del backend (`CHAT_IMAGE_MAX_MB`, `CHAT_IMAGES_PER_MESSAGE`). */
export const MAX_IMAGE_MB = 5
export const MAX_IMAGES_PER_MESSAGE = 4
export const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'] as const
export const IMAGE_ACCEPT = ALLOWED_IMAGE_TYPES.join(',')

const MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024

export function isAllowedImageType(type: string): boolean {
  return (ALLOWED_IMAGE_TYPES as readonly string[]).includes(type)
}

/** Motivo amigable por el que el archivo no se puede adjuntar, o `null` si sirve. */
export function imageRejection(file: File): string | null {
  if (!isAllowedImageType(file.type)) {
    return `“${file.name}” no es una imagen compatible. Usá PNG, JPG, WEBP o GIF.`
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return `“${file.name}” pesa más de ${MAX_IMAGE_MB} MB.`
  }
  if (file.size === 0) {
    return `“${file.name}” está vacía.`
  }
  return null
}

export function tooManyImagesMessage(): string {
  return `Podés adjuntar hasta ${MAX_IMAGES_PER_MESSAGE} imágenes por mensaje.`
}

/** Mensaje corto para una subida fallida; nunca expone detalles internos. */
export function uploadErrorMessage(e: unknown): string {
  if (e instanceof HttpRequestError) {
    if (e.status === 413) return `Pesa más de ${MAX_IMAGE_MB} MB.`
    if (e.status === 422) return 'No es una imagen válida.'
    if (e.status === 429) return 'Demasiadas subidas seguidas. Probá en un rato.'
  }
  return 'No se pudo subir. Reintentá.'
}
