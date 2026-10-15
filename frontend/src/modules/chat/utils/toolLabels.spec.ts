import { describe, expect, it } from 'vitest'
import type { ToolCall } from '../types'
import { groupToolCalls } from './groupToolCalls'
import { getToolKind, getToolLabel } from './toolLabels'

describe('getToolLabel', () => {
  it('mientras corre, usa gerundio con puntos suspensivos', () => {
    expect(getToolLabel('mcp__savi__consultar_datos', 'running')).toBe('Consultando el ERP…')
    expect(getToolLabel('mcp__savi__consultar_libre', 'running')).toBe('Consultando el ERP…')
    expect(getToolLabel('mcp__savi__info_empresa', 'running')).toBe(
      'Revisando los datos de la empresa…',
    )
  })

  it('al terminar, pasa a pasado sin contradecir lo que se ve', () => {
    expect(getToolLabel('mcp__savi__consultar_datos', 'success')).toBe('Consultó el ERP')
    expect(getToolLabel('info_empresa', 'success')).toBe('Revisó los datos de la empresa')
  })

  it('distingue documentos de la empresa del conocimiento del ERP por `tipo`', () => {
    const name = 'mcp__savi__consultar_conocimiento'

    expect(getToolLabel(name, 'running', { tipo: 'documentos' })).toBe(
      'Buscando en los documentos de la empresa…',
    )
    expect(getToolLabel(name, 'success', { tipo: 'documentos' })).toBe('Consultó los documentos')
    expect(getToolLabel(name, 'running', { tipo: 'faq' })).toBe(
      'Buscando en el conocimiento del ERP…',
    )
    expect(getToolLabel(name, 'success', { tipo: 'modulo' })).toBe(
      'Consultó el conocimiento del ERP',
    )
    expect(getToolLabel(name, 'success')).toBe('Consultó el conocimiento del ERP')
  })

  it('nunca muestra "Procesando información" ni el nombre interno de la tool', () => {
    for (const status of ['running', 'success', 'error'] as const) {
      const label = getToolLabel('mcp__savi__algo_nuevo', status)
      expect(label).not.toMatch(/Procesando|mcp__|savi__/)
    }
    expect(getToolLabel('algo_nuevo', 'running')).toBe('Trabajando en su consulta…')
    expect(getToolLabel('algo_nuevo', 'success')).toBe('Listo')
  })

  it('un error no dice que se consultó', () => {
    expect(getToolLabel('mcp__savi__consultar_datos', 'error')).toBe('No se pudo consultar el ERP')
  })
})

describe('getToolKind', () => {
  it('acepta el nombre con y sin prefijo MCP', () => {
    expect(getToolKind('consultar_datos')).toBe('erp')
    expect(getToolKind('mcp__savi__consultar_datos')).toBe('erp')
  })
})

describe('groupToolCalls', () => {
  const call = (id: string, name: string, status: ToolCall['status'], input?: ToolCall['input']) =>
    ({ id, name, status, input }) satisfies ToolCall

  it('agrupa consultas del mismo tipo con contador y las muestra en pasado al terminar', () => {
    const groups = groupToolCalls([
      call('1', 'mcp__savi__consultar_datos', 'success'),
      call('2', 'mcp__savi__consultar_libre', 'success'),
      call('3', 'mcp__savi__consultar_conocimiento', 'success', { tipo: 'documentos' }),
    ])

    expect(groups.map((g) => [g.label, g.count])).toEqual([
      ['Consultó el ERP', 2],
      ['Consultó los documentos', 1],
    ])
  })

  it('si alguna sigue corriendo, el grupo entero se muestra en curso', () => {
    const [group] = groupToolCalls([
      call('1', 'mcp__savi__consultar_datos', 'success'),
      call('2', 'mcp__savi__consultar_datos', 'running'),
    ])

    expect(group?.status).toBe('running')
    expect(group?.label).toBe('Consultando el ERP…')
    expect(group?.count).toBe(2)
  })
})
