import { describe, expect, it } from 'vitest'
import { slugify } from '../download'

describe('slugify', () => {
  it('lowercases and hyphenates spaces', () => {
    expect(slugify('Ventas por mes')).toBe('ventas-por-mes')
  })

  it('strips accents and special characters', () => {
    expect(slugify('Facturación Año 2026')).toBe('facturacion-ano-2026')
  })

  it('trims leading and trailing hyphens', () => {
    expect(slugify('  ¡Hola!  ')).toBe('hola')
  })

  it('falls back when the result is empty', () => {
    expect(slugify('¿?¡!', 'grafica')).toBe('grafica')
  })
})
