import { describe, expect, it } from 'vitest'

import router from '../index'

/**
 * Sin catch-all, una URL desconocida no matchea ninguna ruta y el router
 * renderiza la nada: pantalla en blanco, indistinguible de una app rota.
 */
describe('ruta 404', () => {
  it('resuelve una URL desconocida a la vista de no encontrado', () => {
    expect(router.resolve('/esto-no-existe').name).toBe('not-found')
  })

  it('también atrapa rutas anidadas inexistentes', () => {
    expect(router.resolve('/admin/inventado/mas-hondo').name).toBe('not-found')
  })

  it('no se come las rutas reales', () => {
    expect(router.resolve('/').name).toBe('home')
    expect(router.resolve('/login').name).toBe('login')
    expect(router.resolve('/c/abc').name).toBe('conversation')
    expect(router.resolve('/admin/bases-datos').name).toBe('admin-databases')
  })
})
