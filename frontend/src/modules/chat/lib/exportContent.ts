/**
 * Exportadores de contenido del chat — mensajes sueltos o conversaciones
 * completas — a HTML self-contained, PDF (vía print) y Markdown.
 *
 * Estrategia de captura:
 *   - HTML / PDF: tomamos el DOM ya renderizado por MarkdownRenderer y lo
 *     envolvemos en un documento standalone con CSS embebido. Esto preserva
 *     tablas, listas y código tal como el usuario los vio.
 *     Alternativa descartada: serializar desde el array de mensajes a
 *     HTML reparseando markdown — duplicaría la lógica de render y abriría
 *     diferencias entre lo que se ve y lo que se exporta.
 *
 *   - Markdown: serializamos desde el array de mensajes (NO del DOM),
 *     porque el DOM ya es HTML y convertirlo de vuelta es costoso y
 *     lossy. Para conversación completa armamos cabeceras `## Usuario` /
 *     `## SAVI` separadas con `---`.
 *
 * Inspirado en el patrón ya probado en un backend hermano (aniro-QA),
 * adaptado al stack de SAVI.
 */
import type { UIMessage } from '../types'

// ─────────────────────────────────────────────────────────────────────
// CSS del documento exportado.
// Resolvemos las CSS variables a colores fijos para que el HTML
// standalone se vea bien fuera del tema de la app.
// ─────────────────────────────────────────────────────────────────────
const EXPORT_CSS = `
:root {
  --bg: #ffffff;
  --text: #1a1a1a;
  --text-muted: #555;
  --text-subtle: #888;
  --border: #e5e5e5;
  --bg-subtle: #f5f5f7;
  --bg-elev: #fafafa;
  --brand: #c8102e;
  --brand-soft: #fbe7ea;
}

* { box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  max-width: 820px;
  margin: 2rem auto;
  padding: 0 1.5rem 3rem;
  color: var(--text);
  line-height: 1.65;
  font-size: 14.5px;
  background: var(--bg);
}

.savi-header {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding-bottom: 1rem;
  margin-bottom: 1.75rem;
  border-bottom: 1px solid var(--border);
}
.savi-logo {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: var(--brand);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 0.02em;
}
.savi-title { font-weight: 600; font-size: 14px; color: var(--text); }
.savi-meta  { font-size: 12px; color: var(--text-subtle); margin-top: 2px; }

h1, h2, h3, h4 {
  color: var(--text);
  margin: 1.6em 0 0.6em;
  line-height: 1.3;
  font-weight: 600;
}
h1 { font-size: 1.5rem; }
h2 { font-size: 1.25rem; }
h3 { font-size: 1.1rem; }

p { margin: 0 0 12px; }
strong { font-weight: 600; }

ul, ol { margin: 0 0 12px; padding-left: 1.4em; }
ul li, ol li { margin: 4px 0; }

blockquote {
  margin: 1em 0;
  padding: 0.4em 1em;
  border-left: 3px solid var(--brand);
  color: var(--text-muted);
  background: var(--brand-soft);
  border-radius: 0 6px 6px 0;
}

code {
  background: var(--bg-subtle);
  padding: 0.12em 0.36em;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9em;
}
pre {
  background: var(--bg-subtle);
  padding: 14px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.5;
}
pre code { background: none; padding: 0; }

table {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  font-size: 13.5px;
}
th, td {
  border: 1px solid var(--border);
  padding: 8px 12px;
  text-align: left;
  vertical-align: top;
}
th { background: var(--bg-subtle); font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }

a { color: var(--brand); text-decoration: underline; text-underline-offset: 2px; }
hr { border: none; border-top: 1px solid var(--border); margin: 2em 0; }

/* Diferenciación de turno cuando se exporta una conversación completa */
.savi-turn {
  margin: 2em 0;
  padding: 1.25em 1.5em;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-elev);
  page-break-inside: avoid;
}
.savi-turn--user {
  background: var(--brand-soft);
  border-color: var(--brand-soft);
}
.savi-turn__label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-subtle);
  margin-bottom: 0.6em;
}
.savi-turn--user .savi-turn__label { color: var(--brand); }

@media print {
  body { margin: 0; padding: 12mm 14mm; max-width: none; }
  .savi-header { margin-bottom: 1rem; }
  table, pre, blockquote, .savi-turn { page-break-inside: avoid; }
  h1, h2, h3, h4 { page-break-after: avoid; }
  a { color: var(--text); text-decoration: none; }
}
`

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    switch (c) {
      case '&': return '&amp;'
      case '<': return '&lt;'
      case '>': return '&gt;'
      case '"': return '&quot;'
      default: return '&#39;'
    }
  })
}

export function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    // Quitamos diacríticos (acentos)
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)+/g, '')
    .slice(0, 40)
}

function buildStandaloneHtml(contentHtml: string, title: string): string {
  const date = new Date().toLocaleString('es-CO', {
    dateStyle: 'long',
    timeStyle: 'short',
  })
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>${EXPORT_CSS}</style>
</head>
<body>
<div class="savi-header">
  <div class="savi-logo">S</div>
  <div>
    <div class="savi-title">SAVI — Asistente del ERP</div>
    <div class="savi-meta">${escapeHtml(date)}</div>
  </div>
</div>
${contentHtml}
</body>
</html>`
}

/** Toma el primer heading o las primeras palabras del texto plano. */
function deriveTitle(node: HTMLElement, fallback: string): string {
  const heading = node.querySelector('h1, h2, h3')
  if (heading?.textContent) return heading.textContent.trim().slice(0, 80)
  const text = node.textContent?.trim() ?? fallback
  return text.split('\n')[0]?.slice(0, 80) || fallback
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ─────────────────────────────────────────────────────────────────────
// API pública
// ─────────────────────────────────────────────────────────────────────

export function buildConversationUrl(id: string): string {
  // Apuntamos a `/share/:id` (vista de solo lectura) en lugar de `/c/:id`
  // (vista editable). Esto refleja la convención de productos tipo
  // ChatGPT: el link compartido lleva a un viewer público sin composer
  // ni acciones de edición. Por ahora la vista igualmente requiere
  // sesión — habilitar acceso público requiere un endpoint backend
  // dedicado (TODO documentado en chat_data_access_proposal.md).
  const base = typeof window !== 'undefined' ? window.location.origin : ''
  return `${base}/share/${id}`
}

/**
 * Intenta el Web Share API nativo (sistema). Si el navegador no lo
 * soporta o el usuario lo cancela, devuelve false para que el caller
 * caiga a un fallback (copiar al portapapeles).
 */
export async function tryWebShare(payload: ShareData): Promise<boolean> {
  if (typeof navigator === 'undefined' || !navigator.share) return false
  try {
    await navigator.share(payload)
    return true
  } catch {
    return false
  }
}

/** Exporta `node` como HTML self-contained con CSS embebido. */
export function exportHtml(node: HTMLElement, fallbackTitle = 'respuesta'): void {
  const title = deriveTitle(node, fallbackTitle)
  const html = buildStandaloneHtml(node.outerHTML, title)
  const filename = `savi-${slugify(title) || 'respuesta'}.html`
  downloadBlob(new Blob([html], { type: 'text/html;charset=utf-8' }), filename)
}

/**
 * Abre una ventana nueva con el contenido renderizado y dispara el
 * diálogo de impresión. Desde ahí el usuario elige "Guardar como PDF".
 *
 * Usamos un Blob URL en vez de `document.write` porque:
 *   - `document.write` sobre `about:blank` está cada vez más bloqueado
 *     por los navegadores modernos.
 *   - Sin `noopener` hay problemas de seguridad; con `noopener` el handle
 *     devuelto sería inerte.
 * Con Blob URL el navegador carga el HTML como página normal y podemos
 * llamar `w.print()` confiable.
 */
export function printPdf(node: HTMLElement, fallbackTitle = 'respuesta'): void {
  const title = deriveTitle(node, fallbackTitle)
  const html = buildStandaloneHtml(node.outerHTML, title)
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const w = window.open(url, '_blank')
  if (!w) {
    URL.revokeObjectURL(url)
    return
  }
  let triggered = false
  const triggerPrint = (): void => {
    if (triggered) return
    triggered = true
    try {
      w.focus()
      w.print()
    } catch {
      /* ventana cerrada antes de tiempo — ignorar */
    }
    // El blob debe seguir accesible mientras la pestaña esté viva. 60s
    // alcanza para que el diálogo se abra y el usuario decida.
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }
  w.addEventListener('load', () => setTimeout(triggerPrint, 150), { once: true })
  // Fallback por si el load ya disparó (race en caché caliente).
  setTimeout(() => {
    if (!triggered && w.document?.readyState === 'complete') triggerPrint()
  }, 800)
}

/** Descarga el texto como archivo .md. */
export function downloadMarkdown(text: string, fallbackTitle = 'respuesta'): void {
  const firstLine =
    text
      .split('\n')
      .find((l) => l.trim().length > 0)
      ?.replace(/^#+\s*/, '') ?? fallbackTitle
  const filename = `savi-${slugify(firstLine) || 'respuesta'}.md`
  downloadBlob(new Blob([text], { type: 'text/markdown;charset=utf-8' }), filename)
}

/**
 * Serializa una conversación completa como Markdown.
 *
 * Por qué desde datos y no desde DOM: el DOM ya es HTML renderizado,
 * y convertirlo de vuelta a markdown sería lossy (perdería estructura
 * de tablas, atributos, etc.). El array de mensajes tiene el markdown
 * original que el LLM produjo — es la fuente más fiel.
 */
export function buildConversationMarkdown(
  messages: readonly UIMessage[],
  title: string,
): string {
  const date = new Date().toLocaleString('es-CO', {
    dateStyle: 'long',
    timeStyle: 'short',
  })
  const header = `# ${title}\n\n_Exportada desde SAVI el ${date}._\n\n---\n`
  const turns = messages
    .filter((m) => m.text.trim().length > 0)
    .map((m) => {
      const label = m.role === 'user' ? '## Usuario' : '## SAVI'
      return `${label}\n\n${m.text}`
    })
  return `${header}\n${turns.join('\n\n---\n\n')}\n`
}
