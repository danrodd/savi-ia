/**
 * Referencias a documentos de la empresa dentro del texto del asistente.
 *
 * El modelo cita con `[D1]`, `[D3]`… El backend manda en `sources` solo las
 * referencias válidas, agrupadas por documento. Acá:
 * - las válidas se reemplazan por un número superíndice por DOCUMENTO
 *   (`[D1]` y `[D3]` del mismo documento → `¹`), en el orden de `sources`;
 * - las que no están en `sources` se eliminan (el modelo pudo inventarlas);
 * - mientras `sources` no llegó (streaming), se ocultan todas para no
 *   mostrar códigos crudos.
 *
 * Se usan dígitos superíndice Unicode y no `<sup>`: el markdown se renderiza
 * con `html: false` + DOMPurify, y así no hace falta abrir el sanitizador.
 * Los bloques de código (```) no se tocan.
 */
import type { MessageSource } from '../types'

const REFERENCE = /(\s?)\[D(\d+)\]/g
// Delimitadores de formato markdown. Si la referencia va justo después de
// uno (`**7,5 %** [D1]`), el espacio se conserva: pegar el número al `**`
// de cierre hace que markdown-it ya no lo reconozca y muestre los asteriscos.
const MARKDOWN_CLOSERS = new Set(['*', '_', '~', '`'])
const SUPERSCRIPT_DIGITS = ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹'] as const

export function toSuperscript(value: number): string {
  return String(value)
    .split('')
    .map((digit) => SUPERSCRIPT_DIGITS[Number(digit)])
    .join('')
}

/** Número visible de cada referencia: la posición de su documento en `sources`. */
export function referenceNumbers(sources: MessageSource[]): Map<string, number> {
  const numbers = new Map<string, number>()
  sources.forEach((source, index) => {
    for (const ref of source.refs.length > 0 ? source.refs : [source.ref]) {
      numbers.set(ref, index + 1)
    }
  })
  return numbers
}

function replaceInProse(prose: string, numbers: Map<string, number>): string {
  return prose.replace(REFERENCE, (_match, space: string, digits: string, offset: number) => {
    const number = numbers.get(`D${digits}`)
    if (number === undefined) return ''
    const previous = prose[offset - 1] ?? ''
    const keepSpace = space !== '' && MARKDOWN_CLOSERS.has(previous)
    return `${keepSpace ? space : ''}${toSuperscript(number)}`
  })
}

export function linkCitations(markdown: string, sources: MessageSource[] | undefined): string {
  if (!markdown.includes('[D')) return markdown
  const numbers = referenceNumbers(sources ?? [])
  // Los segmentos impares quedan dentro de un bloque ``` y se preservan.
  return markdown
    .split(/(```[\s\S]*?(?:```|$))/)
    .map((segment, index) => (index % 2 === 1 ? segment : replaceInProse(segment, numbers)))
    .join('')
}

/**
 * Link de una fuente web, solo si es http(s): el texto de una página ajena
 * nunca debe convertirse en un `javascript:` clickeable.
 */
export function webSourceLink(
  url: string | null | undefined,
): { href: string; host: string } | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    return { href: parsed.href, host: parsed.host.replace(/^www\./, '') }
  } catch {
    return null
  }
}
