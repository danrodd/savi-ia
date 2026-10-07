import { computed, onBeforeUnmount, ref } from 'vue'
import { forgetAttachmentUrl } from '../lib/attachmentBlobCache'
import { attachmentService } from '../services/attachmentService'
import type { ChatAttachment, UIAttachment } from '../types'
import {
  imageRejection,
  MAX_IMAGES_PER_MESSAGE,
  tooManyImagesMessage,
  uploadErrorMessage,
} from '../utils/attachments'

export type PendingStatus = 'uploading' | 'done' | 'error'

export interface PendingAttachment {
  key: string
  filename: string
  mime: string
  /** Object URL local de la miniatura. */
  previewUrl: string
  status: PendingStatus
  /** Id del backend; solo cuando `status === 'done'`. */
  id: string | null
  error: string | null
}

interface UploaderOptions {
  upload?: (file: File, signal: AbortSignal) => Promise<ChatAttachment>
  /** Se llama con cada motivo de rechazo (peso, tipo, cantidad). */
  onReject?: (message: string) => void
}

interface Entry {
  item: PendingAttachment
  file: File | null
  controller: AbortController | null
}

let keySeq = 0

/**
 * Cola de imágenes del composer: valida en el cliente, sube apenas se agrega
 * y expone el estado de cada una. Es dueña de los object URLs mientras las
 * imágenes no se envíen; `take()` transfiere esa propiedad al mensaje.
 */
export function useAttachmentUploader(options: UploaderOptions = {}) {
  const upload = options.upload ?? ((file, signal) => attachmentService.upload(file, signal))
  const entries = ref<Entry[]>([])

  const items = computed(() => entries.value.map((e) => e.item))
  const uploading = computed(() => items.value.some((i) => i.status === 'uploading'))
  const hasError = computed(() => items.value.some((i) => i.status === 'error'))
  const ready = computed<UIAttachment[]>(() =>
    items.value
      .filter((i) => i.status === 'done' && i.id !== null)
      .map((i) => ({
        id: i.id as string,
        filename: i.filename,
        mime: i.mime,
        previewUrl: i.previewUrl,
      })),
  )

  function find(key: string): Entry | undefined {
    return entries.value.find((e) => e.item.key === key)
  }

  async function run(entry: Entry): Promise<void> {
    const file = entry.file
    if (!file) return
    const controller = new AbortController()
    entry.controller = controller
    entry.item.status = 'uploading'
    entry.item.error = null
    try {
      const res = await upload(file, controller.signal)
      if (controller.signal.aborted) return
      entry.item.id = res.id
      entry.item.status = 'done'
      entry.file = null
    } catch (e) {
      if (controller.signal.aborted) return
      entry.item.status = 'error'
      entry.item.error = uploadErrorMessage(e)
    } finally {
      if (entry.controller === controller) entry.controller = null
    }
  }

  function addFiles(files: FileList | File[]): void {
    let tooMany = false
    for (const file of Array.from(files)) {
      const rejection = imageRejection(file)
      if (rejection) {
        options.onReject?.(rejection)
        continue
      }
      if (entries.value.length >= MAX_IMAGES_PER_MESSAGE) {
        tooMany = true
        continue
      }
      keySeq++
      const entry: Entry = {
        item: {
          key: `att-${keySeq}`,
          filename: file.name,
          mime: file.type,
          previewUrl: URL.createObjectURL(file),
          status: 'uploading',
          id: null,
          error: null,
        },
        file,
        controller: null,
      }
      entries.value.push(entry)
      // Siempre vía el proxy reactivo para que el spinner/estado reaccione.
      const reactiveEntry = entries.value[entries.value.length - 1] as Entry
      void run(reactiveEntry)
    }
    if (tooMany) options.onReject?.(tooManyImagesMessage())
  }

  function release(entry: Entry): void {
    entry.controller?.abort()
    URL.revokeObjectURL(entry.item.previewUrl)
    if (entry.item.id) forgetAttachmentUrl(entry.item.id)
  }

  function remove(key: string): void {
    const entry = find(key)
    if (!entry) return
    release(entry)
    entries.value = entries.value.filter((e) => e !== entry)
  }

  function retry(key: string): void {
    const entry = find(key)
    if (!entry || entry.item.status !== 'error') return
    void run(entry)
  }

  /**
   * Devuelve las imágenes subidas y vacía la cola SIN revocar sus URLs: pasan
   * a ser del mensaje enviado (que las muestra mientras no hidrata).
   */
  function take(): UIAttachment[] {
    const taken = ready.value
    entries.value = []
    return taken
  }

  /** Vuelve a poner en la cola imágenes ya subidas (turno rechazado). */
  function restore(attachments: UIAttachment[]): void {
    for (const a of attachments) {
      if (entries.value.length >= MAX_IMAGES_PER_MESSAGE) break
      if (entries.value.some((e) => e.item.id === a.id)) continue
      keySeq++
      entries.value.push({
        item: {
          key: `att-${keySeq}`,
          filename: a.filename,
          mime: a.mime,
          previewUrl: a.previewUrl ?? '',
          status: 'done',
          id: a.id,
          error: null,
        },
        file: null,
        controller: null,
      })
    }
  }

  onBeforeUnmount(() => {
    for (const entry of entries.value) release(entry)
    entries.value = []
  })

  return { items, uploading, hasError, ready, addFiles, remove, retry, take, restore }
}
