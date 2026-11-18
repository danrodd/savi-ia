import { describe, expect, it } from 'vitest'

import { isAdminRouteDenied } from '../adminGuard'
import router from '../index'

describe('ruta de Actualizaciones', () => {
  const resolved = router.resolve({ name: 'admin-updates' })

  it('vive bajo /admin', () => {
    expect(resolved.path).toBe('/admin/actualizaciones')
  })

  it('no deja entrar a quien no es administrador', () => {
    expect(isAdminRouteDenied(resolved, { is_admin: false })).toBe(true)
    expect(isAdminRouteDenied(resolved, { is_admin: true })).toBe(false)
  })
})
