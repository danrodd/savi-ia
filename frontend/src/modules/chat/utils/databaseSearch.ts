/**
 * Búsqueda del selector de base del chat.
 *
 * Soporte atiende a muchos clientes: con una lista larga hay que poder
 * escribir parte del código o del nombre. Cada palabra tiene que aparecer
 * (en cualquier orden) y no importan mayúsculas ni tildes, igual que la
 * búsqueda del backend.
 */
import type { AvailableErpDatabase } from '@/modules/admin'

function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

export function filterDatabases(
  databases: readonly AvailableErpDatabase[],
  query: string,
): AvailableErpDatabase[] {
  const words = normalize(query)
    .split(/[\s_]+/)
    .filter(Boolean)
  if (words.length === 0) return [...databases]
  return databases.filter((db) => {
    const haystack = normalize(`${db.code} ${db.name}`).replace(/_/g, ' ')
    return words.every((w) => haystack.includes(w))
  })
}

/**
 * La base de la sesión va primera: es la opción por defecto y la que más
 * se usa. El resto, alfabético por nombre.
 */
export function sortWithSessionFirst(
  databases: readonly AvailableErpDatabase[],
  sessionDatabaseId: string | null,
): AvailableErpDatabase[] {
  return [...databases].sort((a, b) => {
    if (a.id === sessionDatabaseId) return -1
    if (b.id === sessionDatabaseId) return 1
    return a.name.localeCompare(b.name, 'es')
  })
}
