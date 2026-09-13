import type { RouteLocationNormalized } from 'vue-router'

/**
 * El guard es solo UX: el backend valida el rol en cada endpoint. Además
 * `SAVI_ADMIN_LOGINS` no viaja en el token, así que quien entra por ese
 * escape verá la sección solo si el ERP también lo marca como admin.
 */
export function isAdminRouteDenied(
  to: Pick<RouteLocationNormalized, 'matched'>,
  user: { is_admin: boolean } | null,
): boolean {
  const requiresAdmin = to.matched.some((record) => record.meta.requiresAdmin)
  return requiresAdmin && !user?.is_admin
}
