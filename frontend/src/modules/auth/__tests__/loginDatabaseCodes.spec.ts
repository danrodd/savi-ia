import { beforeEach, describe, expect, it } from 'vitest'

import {
  extractDatabaseCode,
  loginSuggestions,
  readRememberedCodes,
  rememberCodeFromLogin,
} from '../utils/loginDatabaseCodes'

class MemoryStorage implements Storage {
  private data = new Map<string, string>()
  get length(): number {
    return this.data.size
  }
  clear(): void {
    this.data.clear()
  }
  getItem(key: string): string | null {
    return this.data.get(key) ?? null
  }
  key(index: number): string | null {
    return [...this.data.keys()][index] ?? null
  }
  removeItem(key: string): void {
    this.data.delete(key)
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value)
  }
}

describe('login database codes', () => {
  let storage: MemoryStorage

  beforeEach(() => {
    storage = new MemoryStorage()
  })

  it('extracts the code after the last @, uppercased', () => {
    expect(extractDatabaseCode('jperez@norte')).toBe('NORTE')
    expect(extractDatabaseCode('a@b@sur')).toBe('SUR')
    expect(extractDatabaseCode('JPEREZ')).toBeNull()
    expect(extractDatabaseCode('JPEREZ@')).toBeNull()
  })

  it('remembers only the code, most recent first, without duplicates', () => {
    rememberCodeFromLogin('jperez@norte', storage)
    rememberCodeFromLogin('otro@sur', storage)
    rememberCodeFromLogin('jperez@NORTE', storage)

    expect(readRememberedCodes(storage)).toEqual(['NORTE', 'SUR'])
    expect(storage.getItem('savi-agent-login-database-codes')).toBe('["NORTE","SUR"]')
  })

  it('does not remember logins without a code', () => {
    rememberCodeFromLogin('JPEREZ', storage)

    expect(readRememberedCodes(storage)).toEqual([])
  })

  it('ignores corrupted storage', () => {
    storage.setItem('savi-agent-login-database-codes', '{not json')

    expect(readRememberedCodes(storage)).toEqual([])
  })

  it('builds full suggestions from what the user typed', () => {
    expect(loginSuggestions('jperez', ['NORTE', 'SUR'])).toEqual(['jperez@NORTE', 'jperez@SUR'])
    expect(loginSuggestions('jperez@no', ['NORTE'])).toEqual(['jperez@NORTE'])
    expect(loginSuggestions('', ['NORTE'])).toEqual([])
  })
})
