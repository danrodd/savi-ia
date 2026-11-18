import { describe, expect, it } from 'vitest'
import {
  AUDIT_ACTION_OPTIONS,
  auditActionLabel,
  authorLabel,
  dbEngineLabel,
  deploymentModeLabel,
  durationLabel,
  formatDay,
  formatMs,
  formatPercent,
  formatUsd,
  freshnessLabel,
  freshnessTone,
  instanceState,
  providerLabel,
  relativeTime,
  toolLabel,
} from '@/lib/format'

describe('frescura de datos', () => {
  it('es verde hasta una hora, ámbar desde una hora y roja desde 24 h', () => {
    expect(freshnessTone(0)).toBe('ok')
    expect(freshnessTone(3599)).toBe('ok')
    expect(freshnessTone(3600)).toBe('warn')
    expect(freshnessTone(24 * 3600 - 1)).toBe('warn')
    expect(freshnessTone(24 * 3600)).toBe('bad')
  })

  it('no inventa un color cuando todavía no hay datos', () => {
    expect(freshnessTone(null)).toBe('muted')
    expect(freshnessLabel(null)).toBe('Sin datos todavía')
  })

  it('redacta «Datos hasta hace N»', () => {
    expect(freshnessLabel(30)).toBe('Datos hasta hace menos de un minuto')
    expect(freshnessLabel(180)).toBe('Datos hasta hace 3 min')
    expect(freshnessLabel(2 * 3600)).toBe('Datos hasta hace 2 h')
    expect(freshnessLabel(3 * 86400)).toBe('Datos hasta hace 3 días')
  })
})

describe('formato', () => {
  it('relativeTime cuenta desde un instante dado', () => {
    const now = new Date('2026-01-01T12:00:00Z')
    expect(relativeTime('2026-01-01T11:57:00Z', now)).toBe('hace 3 min')
    expect(relativeTime(null, now)).toBe('nunca')
  })

  it('durationLabel pasa de minutos a horas y a días', () => {
    expect(durationLabel(59)).toBe('menos de un minuto')
    expect(durationLabel(59 * 60)).toBe('59 min')
    expect(durationLabel(47 * 3600)).toBe('47 h')
    expect(durationLabel(48 * 3600)).toBe('2 días')
  })

  it('usa decimales extra solo en montos chicos', () => {
    expect(formatUsd('1843.22')).toContain('1.843,22')
    expect(formatUsd('0.0105')).toContain('0,0105')
    expect(formatUsd(null)).toBe('—')
    expect(formatUsd('no-es-numero')).toBe('—')
  })

  it('formatea porcentajes, latencias y días', () => {
    expect(formatPercent(0.075)).toBe('7,5%')
    expect(formatPercent(null)).toBe('—')
    expect(formatMs(850)).toBe('850 ms')
    expect(formatMs(2500)).toBe('2,5 s')
    expect(formatDay('2026-01-05')).toBe('05/01/2026')
  })
})

describe('estado de una instancia', () => {
  it('distingue la que nunca se conectó de la que perdió la conexión', () => {
    expect(instanceState({ status: 'active', online: false, last_seen_at: null })).toEqual({
      label: 'Nunca se conectó',
      tone: 'bad',
    })
    expect(
      instanceState({ status: 'active', online: false, last_seen_at: '2026-11-01T10:00:00Z' }),
    ).toEqual({ label: 'Sin conexión', tone: 'warn' })
    expect(instanceState({ status: 'active', online: true, last_seen_at: null }).label).toBe(
      'En línea',
    )
  })

  it('una suspendida o revocada manda sobre la conexión', () => {
    expect(instanceState({ status: 'revoked', online: false, last_seen_at: null }).tone).toBe('bad')
  })
})

describe('nombres de negocio', () => {
  it('traduce los valores técnicos y deja pasar los que no conoce', () => {
    expect(deploymentModeLabel('server')).toBe('Servidor')
    expect(dbEngineLabel('sqlite')).toBe('SQLite (archivo local)')
    expect(providerLabel('openai')).toBe('OpenAI')
    expect(providerLabel(null)).toBe('—')
    expect(toolLabel('info_empresa')).toBe('Datos de la empresa')
    expect(toolLabel('herramienta_nueva')).toBe('herramienta_nueva')
    expect(auditActionLabel('auth.login')).toBe('Inició sesión')
    expect(auditActionLabel('accion.desconocida')).toBe('accion.desconocida')
    expect(authorLabel('cloud-admin')).toBe('Línea de comandos')
    expect(authorLabel('ana@seo.example')).toBe('ana@seo.example')
  })

  it('el filtro de auditoría ofrece cada acción una vez, ordenada por nombre', () => {
    const labels = AUDIT_ACTION_OPTIONS.map((o) => o.label)
    expect(new Set(AUDIT_ACTION_OPTIONS.map((o) => o.value)).size).toBe(AUDIT_ACTION_OPTIONS.length)
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b, 'es')))
  })
})
