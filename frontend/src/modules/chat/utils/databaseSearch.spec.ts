import { describe, expect, it } from 'vitest'

import { filterDatabases, sortWithSessionFirst } from './databaseSearch'

const FARMA = { id: 'a', code: 'FARMACIAS_SIMILARES', name: 'farmacias_similares' }
const FRAMI = { id: 'b', code: 'FRAMI', name: 'frami' }
const SUR = { id: 'c', code: 'SUR_ANDINA', name: 'Sur Andina de Servicios' }
const ALL = [FARMA, FRAMI, SUR]

describe('filterDatabases', () => {
  it('returns everything for an empty query', () => {
    expect(filterDatabases(ALL, '  ')).toEqual(ALL)
  })

  it('matches part of the code or the name, ignoring case', () => {
    expect(filterDatabases(ALL, 'fra')).toEqual([FRAMI])
    expect(filterDatabases(ALL, 'servicios')).toEqual([SUR])
  })

  it('treats underscores as spaces and words in any order', () => {
    expect(filterDatabases(ALL, 'similares farmacias')).toEqual([FARMA])
    expect(filterDatabases(ALL, 'sur_andina')).toEqual([SUR])
  })

  it('ignores accents', () => {
    expect(
      filterDatabases([{ id: 'd', code: 'BOGOTA', name: 'Clínica Bogotá' }], 'clinica'),
    ).toHaveLength(1)
  })

  it('returns nothing when no database matches', () => {
    expect(filterDatabases(ALL, 'medellin')).toEqual([])
  })
})

describe('sortWithSessionFirst', () => {
  it('puts the session database first and the rest by name', () => {
    expect(sortWithSessionFirst([SUR, FARMA, FRAMI], 'b').map((d) => d.code)).toEqual([
      'FRAMI',
      'FARMACIAS_SIMILARES',
      'SUR_ANDINA',
    ])
  })
})
