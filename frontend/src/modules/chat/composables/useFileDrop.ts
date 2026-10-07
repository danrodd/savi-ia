import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

function hasFiles(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes('Files')
}

/**
 * Zona de soltar archivos sobre un elemento. Solo reacciona a arrastres de
 * archivos (no a texto o enlaces) y cuenta entradas/salidas para que pasar el
 * cursor sobre un hijo no apague el estado `dragging`.
 */
export function useFileDrop(
  target: () => HTMLElement | null | undefined,
  onFiles: (files: File[]) => void,
  enabled: () => boolean = () => true,
) {
  const dragging = ref(false)
  let depth = 0

  function onEnter(e: DragEvent): void {
    if (!enabled() || !hasFiles(e)) return
    e.preventDefault()
    depth++
    dragging.value = true
  }

  function onOver(e: DragEvent): void {
    if (!enabled() || !hasFiles(e)) return
    // Sin esto el navegador no habilita el drop y abre el archivo.
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }

  function onLeave(e: DragEvent): void {
    if (!dragging.value || !hasFiles(e)) return
    depth = Math.max(0, depth - 1)
    if (depth === 0) dragging.value = false
  }

  function onDrop(e: DragEvent): void {
    if (!enabled() || !hasFiles(e)) return
    e.preventDefault()
    depth = 0
    dragging.value = false
    const files = Array.from(e.dataTransfer?.files ?? [])
    if (files.length > 0) onFiles(files)
  }

  function bind(el: HTMLElement): void {
    el.addEventListener('dragenter', onEnter)
    el.addEventListener('dragover', onOver)
    el.addEventListener('dragleave', onLeave)
    el.addEventListener('drop', onDrop)
  }

  function unbind(el: HTMLElement): void {
    el.removeEventListener('dragenter', onEnter)
    el.removeEventListener('dragover', onOver)
    el.removeEventListener('dragleave', onLeave)
    el.removeEventListener('drop', onDrop)
  }

  let bound: HTMLElement | null = null
  function sync(): void {
    const el = target() ?? null
    if (el === bound) return
    if (bound) unbind(bound)
    bound = el
    if (bound) bind(bound)
  }

  // El elemento (y su padre) existen recién al montar.
  onMounted(sync)
  watch(target, sync, { flush: 'post', immediate: true })

  onBeforeUnmount(() => {
    if (bound) unbind(bound)
    bound = null
  })

  return { dragging, sync }
}
