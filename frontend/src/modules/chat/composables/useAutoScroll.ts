import { nextTick, onBeforeUnmount, type Ref, ref, watch } from 'vue'

/**
 * Autoscroll inteligente — patrón estándar de chats de IA (ChatGPT/Slack).
 *
 * Estado fuente único: `stickToBottom`. Todo lo demás se deriva de él.
 *
 * - **Carga inicial / cambio de conversación**: scroll instant al fondo.
 * - **Mensaje nuevo del usuario**: scroll al fondo SIEMPRE (acabás de
 *   mandarlo, querés ver tu mensaje y la respuesta).
 * - **Stream del asistente**: scrolea solo si estás cerca del fondo. Si
 *   estás arriba leyendo algo viejo, NO se te roba el foco; en cambio se
 *   prende `hasNewContent` para que la UI muestre el indicador.
 * - **Intención del usuario manda**: un `wheel`/`touch` hacia arriba suelta
 *   el enganche al instante, incluso a mitad de un stream rápido. El scroll
 *   programático no genera esos eventos, así que es señal limpia: si subís,
 *   no te obligamos a bajar; el botón flotante es el único que te baja.
 * - **Botón flotante**: `jumpToBottom()` baja con animación suave (`smooth`)
 *   y reengancha el stream.
 */

/** Forma mínima de mensaje que el autoscroll necesita observar. */
interface ScrollableMessage {
  tempId: string
  role: 'user' | 'assistant'
  text: string
  toolCalls: readonly unknown[]
  done: boolean
}

const SCROLL_THRESHOLD = 80
/** Red de seguridad: si el scroll `smooth` no llega al fondo (porque creció el
 *  contenido), liberamos el flag igual para no congelar la detección. */
const SMOOTH_FALLBACK_MS = 600

export interface UseAutoScroll {
  /** ¿El usuario está pegado al fondo? Fuente de verdad. */
  stickToBottom: Ref<boolean>
  /** Llegó contenido nuevo del stream mientras el usuario estaba arriba. */
  hasNewContent: Ref<boolean>
  /** Salto manual al fondo (botón flotante): baja suave y reengancha el stream. */
  jumpToBottom: () => void
}

export function useAutoScroll(
  container: Ref<HTMLElement | null>,
  messages: () => readonly ScrollableMessage[],
): UseAutoScroll {
  const stickToBottom = ref(true)
  const hasNewContent = ref(false)
  // Mientras `programmaticScroll` está activo, los `scroll` que dispara nuestro
  // propio `scrollTo` no deben actualizar `stickToBottom`.
  let programmaticScroll = false
  let smoothTimer: ReturnType<typeof setTimeout> | undefined
  let lastTouchY: number | null = null

  function scrollToBottom(behavior: ScrollBehavior = 'auto'): void {
    const el = container.value
    if (!el) return
    programmaticScroll = true
    el.scrollTo({ top: el.scrollHeight, behavior })
    if (behavior === 'smooth') {
      // El scroll suave emite múltiples eventos a lo largo de la animación; el
      // flag se libera en `onScroll` al tocar fondo. Este timer es el fallback.
      clearTimeout(smoothTimer)
      smoothTimer = setTimeout(() => {
        programmaticScroll = false
      }, SMOOTH_FALLBACK_MS)
    } else {
      // Instant: el evento `scroll` corre asíncrono; liberamos tras dos frames.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          programmaticScroll = false
        })
      })
    }
  }

  function jumpToBottom(): void {
    stickToBottom.value = true
    hasNewContent.value = false
    nextTick(() => scrollToBottom('smooth'))
  }

  /** El usuario expresó intención de subir: soltamos el enganche al instante. */
  function releaseStick(): void {
    clearTimeout(smoothTimer)
    programmaticScroll = false
    stickToBottom.value = false
  }

  function onScroll(): void {
    const el = container.value
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    if (programmaticScroll) {
      // Durante un scroll programático solo nos interesa detectar que el
      // `smooth` llegó al fondo para liberar el flag y reenganchar.
      if (distance <= SCROLL_THRESHOLD) {
        clearTimeout(smoothTimer)
        programmaticScroll = false
        stickToBottom.value = true
        hasNewContent.value = false
      }
      return
    }
    stickToBottom.value = distance <= SCROLL_THRESHOLD
    // Llegar al fondo a mano apaga el indicador de contenido nuevo.
    if (stickToBottom.value) hasNewContent.value = false
  }

  function onWheel(e: WheelEvent): void {
    if (e.deltaY < 0) releaseStick()
  }

  function onTouchStart(e: TouchEvent): void {
    lastTouchY = e.touches[0]?.clientY ?? null
  }

  function onTouchMove(e: TouchEvent): void {
    const y = e.touches[0]?.clientY ?? null
    // Dedo bajando = el contenido sube = el usuario quiere leer hacia arriba.
    if (y !== null && lastTouchY !== null && y > lastTouchY + 2) releaseStick()
    lastTouchY = y
  }

  // Listeners atados al contenedor real apenas Vue lo monta. Centralizar acá
  // mantiene la vista declarativa (no cuelga 4 handlers en el template).
  watch(
    container,
    (el, _old, onCleanup) => {
      if (!el) return
      el.addEventListener('scroll', onScroll, { passive: true })
      el.addEventListener('wheel', onWheel, { passive: true })
      el.addEventListener('touchstart', onTouchStart, { passive: true })
      el.addEventListener('touchmove', onTouchMove, { passive: true })
      onCleanup(() => {
        el.removeEventListener('scroll', onScroll)
        el.removeEventListener('wheel', onWheel)
        el.removeEventListener('touchstart', onTouchStart)
        el.removeEventListener('touchmove', onTouchMove)
      })
    },
    { immediate: true },
  )

  onBeforeUnmount(() => clearTimeout(smoothTimer))

  // Watch #1: cambios de "estructura" (carga inicial, switch, mensaje nuevo).
  // Decide si forzamos scroll independientemente de `stickToBottom`.
  watch(
    () => {
      const list = messages()
      // Contamos mensajes del usuario, NO "el último es user": al enviar, el
      // store hace push del placeholder del usuario Y del asistente en el mismo
      // tick, así que el último ya es 'assistant'. El conteo de 'user' sí sube.
      let userCount = 0
      for (const m of list) if (m.role === 'user') userCount++
      return {
        length: list.length,
        firstId: list[0]?.tempId,
        userCount,
      }
    },
    (curr, prev) => {
      const conversationChanged = curr.firstId !== prev?.firstId
      const userMessageAdded = curr.userCount > (prev?.userCount ?? 0)
      if (curr.length === 0) return

      // Carga inicial o cambio de conversación → al fondo, ya (instant).
      if (conversationChanged || prev === undefined) {
        stickToBottom.value = true
        hasNewContent.value = false
        // Doble nextTick: el primero deja que Vue renderice el DOM; el
        // segundo espera a que el navegador calcule `scrollHeight` con las
        // alturas reales (importante con markdown pesado, tablas, code blocks).
        nextTick(() => nextTick(() => scrollToBottom('auto')))
        return
      }

      // Enviaste un mensaje nuevo → al fondo SIEMPRE, aunque estuvieras arriba,
      // con animación suave para que se sienta el movimiento hacia tu mensaje.
      // Subir DESPUÉS, durante el stream, es lo que suelta el enganche (vía
      // wheel/touch); eso lo maneja el watch #2.
      if (userMessageAdded) {
        stickToBottom.value = true
        hasNewContent.value = false
        nextTick(() => scrollToBottom('smooth'))
      }
    },
    { immediate: true },
  )

  // Watch #2: cambios de contenido del último mensaje (stream del asistente).
  // Si seguís el fondo, scrolea; si subiste, prende el indicador y nada más.
  watch(
    () =>
      messages()
        .map((m) => `${m.text.length}:${m.toolCalls.length}:${m.done}`)
        .join('|'),
    () => {
      if (stickToBottom.value) {
        nextTick(() => scrollToBottom('auto'))
      } else {
        hasNewContent.value = true
      }
    },
  )

  return { stickToBottom, hasNewContent, jumpToBottom }
}
