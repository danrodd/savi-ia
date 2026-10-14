import { describe, expect, it } from 'vitest'
import { inlineMarkdownToText, renderInlineMarkdown } from '../markdown'

describe('renderInlineMarkdown', () => {
  it('convierte negrita y cursiva en etiquetas, sin mostrar los asteriscos', () => {
    const html = renderInlineMarkdown('**Total** y *neto*')

    expect(html).toContain('<strong>Total</strong>')
    expect(html).toContain('<em>neto</em>')
    expect(html).not.toContain('**')
  })

  it('no envuelve el resultado en un párrafo', () => {
    expect(renderInlineMarkdown('hola')).toBe('hola')
  })

  it('descarta HTML peligroso', () => {
    const html = renderInlineMarkdown('<img src=x onerror=alert(1)> **ok**')

    expect(html).not.toContain('<img')
    expect(html).toContain('<strong>ok</strong>')
  })
})

describe('inlineMarkdownToText', () => {
  it('deja sólo el dato al exportar', () => {
    expect(inlineMarkdownToText('**Total**')).toBe('Total')
    expect(inlineMarkdownToText('`SKU-1` *nuevo*')).toBe('SKU-1 nuevo')
  })

  it('conserva los números tal cual', () => {
    expect(inlineMarkdownToText('1.234.567,50')).toBe('1.234.567,50')
  })
})
