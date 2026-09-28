import { describe, expect, it } from 'vitest'

import {
  estimatePages,
  hostOf,
  isValidUrlInput,
  normalizeUrlInput,
  pagesSummary,
  sectionLabel,
} from '../utils/webSources'

describe('normalizeUrlInput', () => {
  it('completa con https cuando falta el esquema', () => {
    expect(normalizeUrlInput('  www.empresa.com ')).toBe('https://www.empresa.com')
  })

  it('respeta http y https escritos', () => {
    expect(normalizeUrlInput('http://empresa.com')).toBe('http://empresa.com')
    expect(normalizeUrlInput('HTTPS://empresa.com/precios')).toBe('HTTPS://empresa.com/precios')
  })
})

describe('isValidUrlInput', () => {
  it('acepta dominios con o sin esquema', () => {
    expect(isValidUrlInput('www.empresa.com')).toBe(true)
    expect(isValidUrlInput('https://empresa.com.co/tarifas')).toBe(true)
  })

  it('rechaza texto que no es una dirección', () => {
    expect(isValidUrlInput('')).toBe(false)
    expect(isValidUrlInput('empresa')).toBe(false)
    expect(isValidUrlInput('ftp://empresa.com')).toBe(false)
  })
})

describe('sectionLabel', () => {
  it('traduce las secciones de WordPress', () => {
    expect(sectionLabel('wp-sitemap-posts-page-1.xml')).toBe('Páginas')
    expect(sectionLabel('wp-sitemap-posts-post-2.xml')).toBe('Entradas del blog (2)')
    expect(sectionLabel('wp-sitemap-taxonomies-product_cat-1.xml')).toBe('Categorías de productos')
    expect(sectionLabel('wp-sitemap-users-1.xml')).toBe('Autores')
  })

  it('traduce las secciones de Yoast', () => {
    expect(sectionLabel('product-sitemap.xml')).toBe('Productos')
    expect(sectionLabel('post_tag-sitemap.xml')).toBe('Etiquetas del blog')
    expect(sectionLabel('sitemap.xml')).toBe('Mapa del sitio')
  })

  it('deja legible lo desconocido', () => {
    expect(sectionLabel('recetas-sitemap.xml.gz')).toBe('Recetas')
    expect(sectionLabel('wp-sitemap-posts-sedes_locales-1.xml')).toBe('Sedes locales')
    expect(sectionLabel('links')).toBe('Enlaces del sitio')
  })
})

describe('estimatePages', () => {
  const sections = { 'page-sitemap.xml': 12, 'post-sitemap.xml': 40 }

  it('resta las secciones excluidas', () => {
    expect(estimatePages(50, sections, ['post-sitemap.xml'])).toBe(10)
  })

  it('nunca baja de la página raíz', () => {
    expect(estimatePages(30, sections, ['post-sitemap.xml'])).toBe(1)
  })

  it('sin exclusiones devuelve lo que seleccionó el backend', () => {
    expect(estimatePages(50, sections, [])).toBe(50)
  })
})

describe('pagesSummary y hostOf', () => {
  it('resume páginas y omitidas', () => {
    expect(pagesSummary({ mode: 'site', page_count: 17, skipped_count: 3 })).toBe(
      '17 páginas · 3 omitidas',
    )
    expect(pagesSummary({ mode: 'page', page_count: 1, skipped_count: 0 })).toBe('Una página')
  })

  it('muestra el host o la entrada si no es URL', () => {
    expect(hostOf('https://www.surandina.com.co/contacto')).toBe('www.surandina.com.co')
    expect(hostOf('no es url')).toBe('no es url')
  })
})
