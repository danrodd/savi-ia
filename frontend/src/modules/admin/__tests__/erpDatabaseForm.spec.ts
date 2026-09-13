import { describe, expect, it } from 'vitest'

import type { ErpDatabase } from '../types'
import { formValuesFrom, toSaveRequest, validateFormValues } from '../utils/erpDatabaseForm'

const saved: ErpDatabase = {
  id: '23bbe1a1-861c-4359-bb85-0d3e8e9f71c4',
  code: 'NORTE',
  name: 'Farmacias Norte',
  host: 'localhost',
  port: 5432,
  database: 'farmacias_norte',
  username: 'postgres',
  statement_timeout_ms: 60000,
  is_default: false,
  is_active: true,
  credentials_unreadable: false,
  is_usable: true,
  last_connection_ok_at: null,
  created_at: '2026-09-13T00:00:00Z',
  updated_at: '2026-09-13T00:00:00Z',
}

describe('erp database form', () => {
  it('starts edit with an empty password and omits it from the request', () => {
    const values = formValuesFrom(saved)

    expect(values.password).toBe('')
    expect(toSaveRequest(values)).not.toHaveProperty('password')
  })

  it('sends the password when a new one is typed', () => {
    const values = { ...formValuesFrom(saved), password: 's3cret' }

    expect(toSaveRequest(values).password).toBe('s3cret')
  })

  it('normalizes the code to uppercase', () => {
    const values = { ...formValuesFrom(saved), code: ' norte_2 ' }

    expect(toSaveRequest(values).code).toBe('NORTE_2')
  })

  it('rejects a code containing @, the login separator', () => {
    const values = { ...formValuesFrom(saved), code: 'NOR@TE' }

    expect(validateFormValues(values, { requirePassword: false })).toMatch(/código/)
  })

  it('can skip the name so a connection test can propose it', () => {
    const values = { ...formValuesFrom(saved), name: '' }

    expect(validateFormValues(values, { requirePassword: false })).toMatch(/nombre/)
    expect(validateFormValues(values, { requirePassword: false, requireName: false })).toBeNull()
  })

  it('requires a password only when creating', () => {
    const values = formValuesFrom(saved)

    expect(validateFormValues(values, { requirePassword: false })).toBeNull()
    expect(validateFormValues(values, { requirePassword: true })).toMatch(/contraseña/)
  })
})
