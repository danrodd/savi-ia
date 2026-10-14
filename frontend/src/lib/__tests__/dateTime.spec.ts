import { describe, expect, it } from 'vitest'
import { calendarDaysBetween, formatMessageTime } from '../dateTime'

// Bogotá es UTC-5 todo el año: 19:32Z = 14:32 locales.
const NOW = new Date('2026-10-12T19:40:00Z')

describe('formatMessageTime', () => {
  it('menos de un minuto es "Ahora"', () => {
    expect(formatMessageTime('2026-10-12T19:39:30Z', NOW)).toBe('Ahora')
  })

  it('el mismo día muestra "Hoy" con la hora local', () => {
    expect(formatMessageTime('2026-10-12T19:32:00Z', NOW)).toBe('Hoy 14:32')
  })

  it('el día anterior muestra "Ayer"', () => {
    expect(formatMessageTime('2026-10-11T14:10:00Z', NOW)).toBe('Ayer 09:10')
  })

  it('un mensaje de las 23:30 locales sigue siendo de "Ayer" aunque en UTC sea otro día', () => {
    expect(formatMessageTime('2026-10-12T04:30:00Z', NOW)).toBe('Ayer 23:30')
  })

  it('días anteriores muestran día y mes abreviado', () => {
    expect(formatMessageTime('2026-10-06T19:32:00Z', NOW)).toBe('6 oct 14:32')
  })

  it('otro año agrega el año', () => {
    expect(formatMessageTime('2025-03-02T15:05:00Z', NOW)).toBe('2 mar 2025 10:05')
  })

  it('fecha inválida devuelve vacío', () => {
    expect(formatMessageTime('no-es-fecha', NOW)).toBe('')
  })
})

describe('calendarDaysBetween', () => {
  it('cuenta días de calendario locales, no bloques de 24 horas', () => {
    const late = new Date('2026-10-12T04:30:00Z') // 11 oct 23:30 local
    expect(calendarDaysBetween(late, NOW)).toBe(1)
  })
})
