import { describe, expect, it } from 'vitest'

import { M } from '@/modules/permisos'

import { SUGGESTIONS } from '../suggestions'

// Prueba del 2026-11-25: la pantalla de inicio sugería "¿Cuánta depreciación se
// calculó este mes?", que el catálogo de datos no cubre. Estos módulos no tienen
// entidades en el catálogo; si algún día las tienen, se agregan sus preguntas.
const OUTSIDE_THE_CATALOG = [M.NOMINA, M.ACTIVOFIJO, M.CARTERAFINANCIERA]

describe('sugerencias de la pantalla de inicio', () => {
  it('no ofrecen módulos que el catálogo no cubre', () => {
    const outside = SUGGESTIONS.filter(
      (s) => s.module !== null && OUTSIDE_THE_CATALOG.includes(s.module),
    )
    expect(outside).toEqual([])
  })

  it('no repiten preguntas', () => {
    const prompts = SUGGESTIONS.map((s) => s.prompt)
    expect(new Set(prompts).size).toBe(prompts.length)
  })
})
