import { describe, expect, it } from 'vitest'
import type { Conversation } from '../types'
import {
  filterConversations,
  groupConversations,
  isUntouchedConversation,
  normalizeSearch,
  visibleConversations,
} from './conversationGroups'

// 12 oct 2026, 14:40 en Bogotá.
const NOW = new Date('2026-10-12T19:40:00Z')

function conv(id: string, title: string, updatedAt: string, extra: Partial<Conversation> = {}) {
  return {
    id,
    user_id: '1',
    erp_database_id: null,
    title,
    title_locked: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: updatedAt,
    ...extra,
  } satisfies Conversation
}

describe('normalizeSearch', () => {
  it('ignora mayúsculas y tildes', () => {
    expect(normalizeSearch('  Facturación  ')).toBe('facturacion')
  })
})

describe('filterConversations', () => {
  const list = [
    conv('a', 'Ventas de enero', '2026-10-12T15:00:00Z'),
    conv('b', 'Facturación de marzo', '2026-10-12T14:00:00Z'),
  ]

  it('busca sin importar tildes ni mayúsculas', () => {
    expect(filterConversations(list, 'FACTURACION').map((c) => c.id)).toEqual(['b'])
  })

  it('exige todas las palabras, en cualquier orden', () => {
    expect(filterConversations(list, 'enero ventas').map((c) => c.id)).toEqual(['a'])
    expect(filterConversations(list, 'enero marzo')).toEqual([])
  })

  it('sin texto devuelve todo', () => {
    expect(filterConversations(list, '   ')).toHaveLength(2)
  })
})

describe('groupConversations', () => {
  it('reparte en Hoy, Ayer, Últimos 7 días, Este mes y Anteriores', () => {
    const groups = groupConversations(
      [
        conv('hoy', 'a', '2026-10-12T18:00:00Z'),
        conv('ayer', 'b', '2026-10-11T18:00:00Z'),
        conv('semana', 'c', '2026-10-07T18:00:00Z'),
        conv('mes', 'd', '2026-10-02T18:00:00Z'),
        conv('viejo', 'e', '2026-08-02T18:00:00Z'),
      ],
      NOW,
    )

    expect(groups.map((g) => [g.label, g.items.map((c) => c.id)])).toEqual([
      ['Hoy', ['hoy']],
      ['Ayer', ['ayer']],
      ['Últimos 7 días', ['semana']],
      ['Este mes', ['mes']],
      ['Anteriores', ['viejo']],
    ])
  })

  it('omite los grupos vacíos y conserva el orden recibido', () => {
    const groups = groupConversations(
      [conv('1', 'a', '2026-10-12T18:00:00Z'), conv('2', 'b', '2026-10-12T16:00:00Z')],
      NOW,
    )

    expect(groups).toHaveLength(1)
    expect(groups[0]?.items.map((c) => c.id)).toEqual(['1', '2'])
  })
})

describe('conversaciones sin uso', () => {
  const created = '2026-10-12T18:00:00Z'
  const empty = conv('vacia', 'Nueva conversación', created, {
    created_at: created,
    message_count: 0,
  })

  it('solo es vacía cuando el backend informa cero mensajes', () => {
    expect(isUntouchedConversation(empty)).toBe(true)
    expect(isUntouchedConversation({ ...empty, message_count: 2 })).toBe(false)
  })

  it('el título o las fechas no deciden: una real con título por defecto se ve', () => {
    // Autotítulo fallido: título por defecto, sin lock y fechas iguales.
    const realUntitled = { ...empty, message_count: 4 }

    expect(isUntouchedConversation(realUntitled)).toBe(false)
    expect(visibleConversations([realUntitled], null)).toHaveLength(1)
  })

  it('sin message_count (backend anterior) no se oculta nada', () => {
    const legacy = conv('vieja', 'Nueva conversación', created, { created_at: created })

    expect(isUntouchedConversation(legacy)).toBe(false)
    expect(visibleConversations([legacy], null)).toHaveLength(1)
  })

  it('se ocultan de la lista salvo la que está abierta', () => {
    const real = conv('real', 'Ventas', created, { created_at: created, message_count: 3 })

    expect(visibleConversations([empty, real], null).map((c) => c.id)).toEqual(['real'])
    expect(visibleConversations([empty, real], 'vacia').map((c) => c.id)).toEqual(['vacia', 'real'])
  })
})
