import { type MaybeRefOrGetter, ref, toValue, watchEffect } from 'vue'
import { getAttachmentUrl, peekAttachmentUrl } from '../lib/attachmentBlobCache'

export type AttachmentUrlStatus = 'idle' | 'loading' | 'ready' | 'error'

/** Object URL (autenticado y cacheado) de un adjunto del chat. */
export function useAttachmentUrl(id: MaybeRefOrGetter<string | null>) {
  const url = ref<string | null>(null)
  const status = ref<AttachmentUrlStatus>('idle')

  watchEffect((onCleanup) => {
    const current = toValue(id)
    let stale = false
    onCleanup(() => {
      stale = true
    })
    if (!current) {
      url.value = null
      status.value = 'idle'
      return
    }
    const cached = peekAttachmentUrl(current)
    if (cached) {
      url.value = cached
      status.value = 'ready'
      return
    }
    url.value = null
    status.value = 'loading'
    getAttachmentUrl(current).then(
      (resolved) => {
        if (stale) return
        url.value = resolved
        status.value = 'ready'
      },
      () => {
        if (stale) return
        status.value = 'error'
      },
    )
  })

  return { url, status }
}
