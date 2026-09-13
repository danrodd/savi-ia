/**
 * Códigos de cliente (`USUARIO@CODIGO`) que este equipo ya usó con éxito.
 *
 * Es historial local del navegador: nunca se consulta al backend, porque
 * un listado público de clientes permitiría enumerarlos. Solo se guarda el
 * código, jamás el usuario ni la contraseña.
 */
import { STORAGE_KEYS } from '@/lib/storageKeys'

const MAX_CODES = 10

/** Mismo criterio que el backend: el separador válido es la última `@`. */
export function extractDatabaseCode(login: string): string | null {
  const at = login.lastIndexOf('@')
  if (at === -1) return null
  const code = login.slice(at + 1).trim().toUpperCase()
  return code === '' ? null : code
}

export function readRememberedCodes(storage: Storage = window.localStorage): string[] {
  try {
    const parsed: unknown = JSON.parse(storage.getItem(STORAGE_KEYS.LOGIN_DATABASE_CODES) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((c): c is string => typeof c === 'string') : []
  } catch {
    return []
  }
}

export function rememberCodeFromLogin(login: string, storage: Storage = window.localStorage): void {
  const code = extractDatabaseCode(login)
  if (!code) return
  const codes = [code, ...readRememberedCodes(storage).filter((c) => c !== code)].slice(0, MAX_CODES)
  storage.setItem(STORAGE_KEYS.LOGIN_DATABASE_CODES, JSON.stringify(codes))
}

/** Sugerencias completas para el `<datalist>`, combinando lo tipeado antes de la `@`. */
export function loginSuggestions(typed: string, codes: string[]): string[] {
  const at = typed.lastIndexOf('@')
  const user = (at === -1 ? typed : typed.slice(0, at)).trim()
  if (!user) return []
  return codes.map((code) => `${user}@${code}`)
}
