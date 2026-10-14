/**
 * El ERP guarda los nombres en mayúsculas ("USUARIO QA SAVI"): en pantalla se
 * leen mejor en formato título.
 */

const LOWERCASE_PARTICLES = new Set(['de', 'del', 'la', 'las', 'los', 'y', 'e'])

export function toTitleCase(value: string | null | undefined): string {
  if (!value) return ''
  return value
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word, i) => {
      const lower = word.toLocaleLowerCase('es')
      if (i > 0 && LOWERCASE_PARTICLES.has(lower)) return lower
      return lower.charAt(0).toLocaleUpperCase('es') + lower.slice(1)
    })
    .join(' ')
}

/** Primer nombre en formato título; `fallback` si no hay nombre. */
export function firstNameOf(value: string | null | undefined, fallback = ''): string {
  const first = toTitleCase(value).split(' ')[0]
  return first || fallback
}
