import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true,
})

const defaultLinkRender =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

function setAttr(
  token: {
    attrIndex: (n: string) => number
    attrs: [string, string][] | null
    attrPush: (a: [string, string]) => void
  },
  name: string,
  value: string,
): void {
  const i = token.attrIndex(name)
  if (i < 0) {
    token.attrPush([name, value])
    return
  }
  const attr = token.attrs?.[i]
  if (attr) attr[1] = value
}

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  if (token) {
    setAttr(token, 'target', '_blank')
    setAttr(token, 'rel', 'noopener noreferrer')
  }
  return defaultLinkRender(tokens, idx, options, env, self)
}

export function renderMarkdown(source: string): string {
  const raw = md.render(source)
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target', 'rel'],
  })
}

/**
 * Formato en línea (negrita, cursiva, código, enlaces) sin envolver en un
 * párrafo. Es lo que necesita una celda de tabla: `**Total**` se ve en negrita
 * en lugar de mostrar los asteriscos.
 */
export function renderInlineMarkdown(source: string): string {
  return DOMPurify.sanitize(md.renderInline(source), {
    ADD_ATTR: ['target', 'rel'],
  })
}

/** Texto de una celda sin las marcas de formato, para exportar a CSV/Excel. */
export function inlineMarkdownToText(source: string): string {
  const [inline] = md.parseInline(source, {})
  const parts = (inline?.children ?? []).map((t) => {
    if (t.type === 'text' || t.type === 'code_inline') return t.content
    if (t.type === 'softbreak' || t.type === 'hardbreak') return ' '
    return ''
  })
  return parts.join('')
}
