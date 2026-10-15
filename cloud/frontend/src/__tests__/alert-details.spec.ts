import { describe, expect, it } from 'vitest'
import { alertDetail } from '@/lib/alertDetails'

const detail = (rule_code: string, details: Record<string, unknown>) =>
  alertDetail({ rule_code, details })

describe('detalle legible de las alertas', () => {
  it('instancia sin conexión', () => {
    expect(detail('instance_offline', { instance: 'Caja 1', silent_minutes: 180 })).toBe(
      'Instancia Caja 1 · Sin contacto hace 3 h',
    )
  })

  it('envío detenido lista cada flujo con sus horas', () => {
    expect(detail('sync_stalled', { instance: 'Caja 1', streams: { ventas: 8, turnos: 1 } })).toBe(
      'Instancia Caja 1 · Envíos detenidos: ventas (8 horas sin avanzar), turnos (1 hora sin avanzar)',
    )
  })

  it('reloj desfasado indica el sentido', () => {
    expect(detail('clock_skew', { instance: 'Caja 1', skew_seconds: -600 })).toBe(
      'Instancia Caja 1 · Reloj atrasado 10 min',
    )
    expect(detail('clock_skew', { instance: 'Caja 1', skew_seconds: 900 })).toContain('adelantado')
  })

  it('pico de errores con porcentaje', () => {
    expect(detail('error_rate_spike', { turns: 40, errors: 12, rate: 0.3 })).toMatch(
      /^12 turnos con error de 40 · Tasa de error 30\s?%$/,
    )
  })

  it('pico de costo con dinero formateado', () => {
    const text = detail('cost_spike', { cost_usd: '12.500000', median_14d_usd: '3' })
    expect(text).toContain('Costo de hoy')
    expect(text).toContain('12,50')
    expect(text).toContain('Mediana de los 14 días previos')
  })

  it('avisos técnicos traducidos, con respaldo para códigos nuevos', () => {
    expect(
      detail('instance_warning', { instance: 'Caja 1', warnings: ['cert_expired', 'otro_nuevo'] }),
    ).toBe('Instancia Caja 1 · Certificado vencido, otro_nuevo')
  })

  it('instancia desactualizada', () => {
    expect(
      detail('instance_outdated', { instance: 'Caja 1', version: 'v1.0', latest: 'v1.2' }),
    ).toBe('Instancia Caja 1 · Versión v1.0 · Última publicada v1.2')
  })

  it('suscripción por vencer y vencida', () => {
    expect(detail('subscription_due', { valid_until: '2026-10-03', days_left: 1 })).toBe(
      'Vence el 03/10/2026 · quedan 1 día',
    )
    expect(detail('subscription_due', { valid_until: '2026-10-03', days_left: 0 })).toBe(
      'Vence el 03/10/2026 · hoy',
    )
    expect(detail('subscription_due', { valid_until: '2026-09-30', days_left: -3 })).toBe(
      'Venció el 30/09/2026 · hace 3 días',
    )
  })

  it('sin uso', () => {
    expect(detail('no_usage', { days: 14 })).toBe('Sin turnos en los últimos 14 días')
  })

  it('una regla desconocida o con valores inesperados cae a clave: valor', () => {
    expect(detail('regla_nueva', { a: 1, b: { c: 2 } })).toBe('a: 1 · b: {"c":2}')
    expect(detail('instance_offline', { silent_minutes: 'mucho' })).toBe('silent_minutes: mucho')
  })

  it('sin detalles no devuelve nada', () => {
    expect(detail('no_usage', {})).toBe('')
  })
})
