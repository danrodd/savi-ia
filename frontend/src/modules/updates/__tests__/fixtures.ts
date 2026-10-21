import type { UpdateStatus } from '../types'

export function status(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    enabled: true,
    state: 'recommended',
    current_version: 'v1.3.2',
    available_version: 'v1.4.0',
    notes: 'Corrige la pantalla en blanco.',
    published_at: '2026-11-02T15:00:00Z',
    size: 1000,
    deadline: null,
    can_apply: true,
    phase: 'idle',
    downloaded_bytes: 0,
    error: null,
    checked_at: '2026-11-02T15:00:00Z',
    ...overrides,
  }
}
