import type { ErpDatabase, ErpDatabaseFormValues, SaveErpDatabaseRequest } from '../types'

export const DATABASE_CODE_PATTERN = /^[A-Za-z0-9_-]{2,32}$/

export function emptyFormValues(): ErpDatabaseFormValues {
  return {
    code: '',
    name: '',
    host: 'localhost',
    port: 5432,
    database: '',
    username: '',
    password: '',
    statement_timeout_ms: 60000,
  }
}

/** La contraseña nunca viene del backend: al editar arranca vacía. */
export function formValuesFrom(db: ErpDatabase): ErpDatabaseFormValues {
  return {
    code: db.code,
    name: db.name,
    host: db.host,
    port: db.port,
    database: db.database,
    username: db.username,
    password: '',
    statement_timeout_ms: db.statement_timeout_ms,
  }
}

/** Contraseña vacía se omite: el backend la interpreta como "conservar la guardada". */
export function toSaveRequest(values: ErpDatabaseFormValues): SaveErpDatabaseRequest {
  const request: SaveErpDatabaseRequest = {
    code: values.code.trim().toUpperCase(),
    name: values.name.trim(),
    host: values.host.trim(),
    port: Number(values.port),
    database: values.database.trim(),
    username: values.username.trim(),
    statement_timeout_ms: Number(values.statement_timeout_ms),
  }
  if (values.password !== '') request.password = values.password
  return request
}

export function validateFormValues(
  values: ErpDatabaseFormValues,
  { requirePassword, requireName = true }: { requirePassword: boolean; requireName?: boolean },
): string | null {
  if (!DATABASE_CODE_PATTERN.test(values.code.trim())) {
    return 'El código debe tener entre 2 y 32 caracteres: letras, números, guion o guion bajo.'
  }
  if (requireName && !values.name.trim()) return 'El nombre es obligatorio.'
  if (!values.host.trim()) return 'El host es obligatorio.'
  const port = Number(values.port)
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'El puerto debe ser un número entre 1 y 65535.'
  }
  if (!values.database.trim()) return 'El nombre de la base es obligatorio.'
  if (!values.username.trim()) return 'El usuario es obligatorio.'
  if (requirePassword && values.password === '') return 'La contraseña es obligatoria.'
  const timeout = Number(values.statement_timeout_ms)
  if (!Number.isInteger(timeout) || timeout < 1000 || timeout > 600000) {
    return 'El tiempo máximo de consulta debe estar entre 1000 y 600000 ms.'
  }
  return null
}
