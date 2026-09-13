import { describe, expect, it } from 'vitest'
import type { RouteRecordNormalized } from 'vue-router'

import { isAdminRouteDenied } from '../adminGuard'

function routeWith(...metas: Record<string, unknown>[]) {
  return { matched: metas.map((meta) => ({ meta }) as unknown as RouteRecordNormalized) }
}

describe('isAdminRouteDenied', () => {
  const adminChild = routeWith({ requiresAuth: true, requiresAdmin: true }, {})

  it('denies a non-admin on a child of an admin route', () => {
    expect(isAdminRouteDenied(adminChild, { is_admin: false })).toBe(true)
  })

  it('denies when there is no user', () => {
    expect(isAdminRouteDenied(adminChild, null)).toBe(true)
  })

  it('allows an admin', () => {
    expect(isAdminRouteDenied(adminChild, { is_admin: true })).toBe(false)
  })

  it('ignores routes that do not require admin', () => {
    expect(isAdminRouteDenied(routeWith({ requiresAuth: true }), { is_admin: false })).toBe(false)
  })
})
