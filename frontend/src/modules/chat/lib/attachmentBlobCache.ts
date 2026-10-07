import { attachmentService } from '../services/attachmentService'

/**
 * Caché de object URLs de las imágenes adjuntas, por id de adjunto.
 *
 * Decisión: vive todo el tiempo que dure la sesión de la página y NO se revoca
 * al desmontar cada miniatura. Un hilo se remonta seguido (cambiar de
 * conversación, editar, hidratar) y refetchear la misma imagen cada vez sería
 * peor que retener unos pocos MB; el límite es 4 imágenes de ≤5 MB por mensaje
 * y el navegador libera todo al recargar. `clearAttachmentCache()` las revoca
 * a mano (p. ej. al cerrar sesión).
 *
 * También se siembra con la miniatura local de la subida (`seed`): así el
 * mensaje recién enviado no vuelve a pedir al servidor una imagen que ya
 * tenemos en memoria.
 */
const urls = new Map<string, string>()
const inflight = new Map<string, Promise<string>>()

export function peekAttachmentUrl(id: string): string | null {
  return urls.get(id) ?? null
}

export function seedAttachmentUrl(id: string, url: string): void {
  if (!urls.has(id)) urls.set(id, url)
}

/** Olvida el id sin revocar la URL (su dueño decide cuándo). */
export function forgetAttachmentUrl(id: string): void {
  urls.delete(id)
}

export function getAttachmentUrl(id: string): Promise<string> {
  const cached = urls.get(id)
  if (cached) return Promise.resolve(cached)
  const pending = inflight.get(id)
  if (pending) return pending

  const request = attachmentService
    .download(id)
    .then((blob) => {
      const url = URL.createObjectURL(blob)
      urls.set(id, url)
      return url
    })
    .finally(() => inflight.delete(id))
  inflight.set(id, request)
  return request
}

export function clearAttachmentCache(): void {
  for (const url of urls.values()) URL.revokeObjectURL(url)
  urls.clear()
  inflight.clear()
}
