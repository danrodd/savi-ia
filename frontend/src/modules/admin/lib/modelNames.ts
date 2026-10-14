/**
 * Nombres legibles para los identificadores de modelo.
 *
 * `gpt-6.1-sol` no le dice nada a quien administra SAVI; "GPT-6.1 Sol" sí.
 * Solo se traducen los patrones que conocemos: ante cualquier otro
 * identificador se devuelve tal cual (el id original queda además como
 * tooltip en la pantalla), así nunca se inventa un nombre equivocado.
 */

const CLAUDE_MODERN = /^claude-(opus|sonnet|haiku)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(?:-latest)?$/
const CLAUDE_LEGACY = /^claude-(\d+)(?:-(\d{1,2}))?-(opus|sonnet|haiku)(?:-\d{8})?(?:-latest)?$/
const OPENAI_GPT = /^gpt-(\d+(?:\.\d+)?o?)((?:-[a-z][a-z0-9]*)*)(?:-\d{4}-\d{2}-\d{2})?$/
const GEMINI_SLUG = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1)
}

function words(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map((w) => (/^\d/.test(w) ? w : capitalize(w)))
    .join(' ')
}

function claudeVersion(major: string, minor: string | undefined): string {
  return minor ? `${major}.${minor}` : major
}

export function friendlyModelName(id: string | null | undefined): string {
  if (!id) return ''
  const model = id.trim()
  const lower = model.toLowerCase()

  const modern = CLAUDE_MODERN.exec(lower)
  if (modern) {
    return `Claude ${capitalize(modern[1] ?? '')} ${claudeVersion(modern[2] ?? '', modern[3])}`
  }
  const legacy = CLAUDE_LEGACY.exec(lower)
  if (legacy) {
    return `Claude ${capitalize(legacy[3] ?? '')} ${claudeVersion(legacy[1] ?? '', legacy[2])}`
  }

  const gpt = OPENAI_GPT.exec(lower)
  if (gpt) {
    const rest = words(gpt[2] ?? '')
    return rest ? `GPT-${gpt[1]} ${rest}` : `GPT-${gpt[1]}`
  }

  // Los snapshots de vista previa llevan fechas y sufijos que no vale la pena
  // reinterpretar: se muestran con su id.
  if (!/preview|exp/.test(lower)) {
    const slug = lower.startsWith('gemini-') ? lower.slice(7).replace(/-latest$/, '') : ''
    if (slug && GEMINI_SLUG.test(slug)) return `Gemini ${words(slug)}`
  }

  return model
}
