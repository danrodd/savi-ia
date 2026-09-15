import { describe, expect, it } from 'vitest'

import type { CompanyDocument } from '../types'

/**
 * Filtrado del listado de documentos.
 *
 * La lógica vive en la vista (un `computed` sobre la lista ya cargada), así
 * que se prueba acá la misma regla: sin esto, cada cambio de la condición
 * dependería de mirar la pantalla.
 */

type Grupo = 'todos' | 'listo' | 'en_proceso' | 'con_problema'

const GRUPOS = {
  listo: ['ready'],
  en_proceso: ['pending', 'processing'],
  con_problema: ['failed', 'no_text'],
} as const

function filtrar(documentos: CompanyDocument[], termino: string, grupo: Grupo): CompanyDocument[] {
  const term = termino.trim().toLowerCase()
  return documentos.filter((document) => {
    const coincideTexto =
      !term ||
      document.title.toLowerCase().includes(term) ||
      document.original_filename.toLowerCase().includes(term)
    const coincideEstado =
      grupo === 'todos' || (GRUPOS[grupo] as readonly string[]).includes(document.status)
    return coincideTexto && coincideEstado
  })
}

function documento(partes: Partial<CompanyDocument>): CompanyDocument {
  return {
    id: crypto.randomUUID(),
    title: 'Manual de caja',
    original_filename: 'manual-caja.pdf',
    status: 'ready',
    ...partes,
  } as CompanyDocument
}

// Nombres de archivo distintos a propósito: con el mismo por defecto, buscar
// "caja" coincidía con todos y el test pasaba por el motivo equivocado.
const DOCUMENTOS = [
  documento({ title: 'Manual de caja', original_filename: 'manual-caja.pdf' }),
  documento({ title: 'Política de devoluciones', original_filename: 'devoluciones.txt' }),
  documento({
    title: 'Reglamento interno',
    original_filename: 'reglamento.pdf',
    status: 'processing',
  }),
  documento({ title: 'Acta rota', original_filename: 'acta.pdf', status: 'failed' }),
  documento({
    title: 'Escaneado sin texto',
    original_filename: 'escaneado.pdf',
    status: 'no_text',
  }),
]

describe('filtrado de documentos', () => {
  it('sin filtros devuelve todo', () => {
    expect(filtrar(DOCUMENTOS, '', 'todos')).toHaveLength(5)
  })

  it('busca por título sin importar mayúsculas ni acentos escritos igual', () => {
    const resultado = filtrar(DOCUMENTOS, 'POLÍTICA', 'todos')

    expect(resultado).toHaveLength(1)
    expect(resultado[0]?.title).toBe('Política de devoluciones')
  })

  it('busca también por nombre de archivo', () => {
    /** El título se puede editar: quien subió `devoluciones.txt` lo busca así. */
    const resultado = filtrar(DOCUMENTOS, 'devoluciones.txt', 'todos')

    expect(resultado).toHaveLength(1)
  })

  it('ignora espacios alrededor del término', () => {
    expect(filtrar(DOCUMENTOS, '   caja  ', 'todos')).toHaveLength(1)
  })

  it('agrupa pendiente y procesando como "en proceso"', () => {
    expect(filtrar(DOCUMENTOS, '', 'en_proceso')).toHaveLength(1)
  })

  it('agrupa error y sin texto como "con problemas"', () => {
    /** Los dos piden la misma acción: revisar el archivo y reprocesar. */
    expect(filtrar(DOCUMENTOS, '', 'con_problema')).toHaveLength(2)
  })

  it('combina texto y estado', () => {
    expect(filtrar(DOCUMENTOS, 'acta', 'con_problema')).toHaveLength(1)
    expect(filtrar(DOCUMENTOS, 'acta', 'listo')).toHaveLength(0)
  })

  it('un término sin coincidencias devuelve vacío', () => {
    expect(filtrar(DOCUMENTOS, 'inventario', 'todos')).toHaveLength(0)
  })
})
