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
