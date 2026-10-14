import { describe, expect, it } from 'vitest'
import { firstNameOf, toTitleCase } from '../personName'

describe('toTitleCase', () => {
  it('pasa mayúsculas del ERP a formato título', () => {
    expect(toTitleCase('USUARIO QA SAVI')).toBe('Usuario Qa Savi')
  })

  it('deja las partículas en minúscula', () => {
    expect(toTitleCase('MARIA DE LOS ANGELES')).toBe('Maria de los Angeles')
  })

  it('tolera vacío y espacios repetidos', () => {
    expect(toTitleCase(null)).toBe('')
    expect(toTitleCase('  ana   perez ')).toBe('Ana Perez')
  })
})

describe('firstNameOf', () => {
  it('toma el primer nombre', () => {
    expect(firstNameOf('USUARIO QA SAVI')).toBe('Usuario')
  })

  it('usa el fallback si no hay nombre', () => {
    expect(firstNameOf('', 'saviqa')).toBe('saviqa')
  })
})
