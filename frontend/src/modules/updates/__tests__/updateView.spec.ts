import { describe, expect, it } from 'vitest'

import {
  bannerMessage,
  INSTALLING_MAX_MS,
  installStalled,
  noticeKind,
  progressMessage,
  progressPercent,
  restartedWithNewVersion,
  resultNotice,
  SNOOZE_MS,
} from '../utils/updateView'
import { installRecord, status } from './fixtures'

const NOW = Date.parse('2026-11-02T15:00:00Z')

describe('noticeKind', () => {
  it('shows nothing when updates are off or up to date', () => {
    expect(noticeKind(null, NOW, null)).toBe('none')
    expect(noticeKind(status({ enabled: false }), NOW, null)).toBe('none')
    expect(noticeKind(status({ state: 'up_to_date' }), NOW, null)).toBe('none')
  })

  it('shows the banner for recommended and required updates', () => {
    expect(noticeKind(status(), NOW, null)).toBe('banner')
    expect(noticeKind(status({ state: 'required' }), NOW, null)).toBe('banner')
  })

  it('hides the banner while snoozed and brings it back after 24 h', () => {
    const until = NOW + SNOOZE_MS
    expect(noticeKind(status(), NOW, until)).toBe('none')
    expect(noticeKind(status(), until, until)).toBe('banner')
  })

  it('blocks even when snoozed', () => {
    expect(noticeKind(status({ state: 'blocked' }), NOW, NOW + SNOOZE_MS)).toBe('blocked')
  })

  it('shows a failed attempt even when snoozed, so it can be retried', () => {
    const failed = status({ phase: 'failed', error: 'Intente de nuevo.' })
    expect(noticeKind(failed, NOW, NOW + SNOOZE_MS)).toBe('banner')
  })

  it('shows progress while downloading or installing', () => {
    expect(noticeKind(status({ phase: 'downloading' }), NOW, null)).toBe('progress')
    expect(noticeKind(status({ phase: 'waiting_turns' }), NOW, null)).toBe('progress')
    expect(noticeKind(status({ phase: 'installing', state: 'blocked' }), NOW, null)).toBe(
      'progress',
    )
  })
})

describe('messages', () => {
  it('names the new version', () => {
    expect(bannerMessage(status())).toBe('Hay una versión nueva de SAVI (v1.4.0).')
  })

  it('includes the deadline when the update is required', () => {
    const message = bannerMessage(status({ state: 'required', deadline: '2026-11-05T15:00:00Z' }))
    expect(message).toMatch(/^Debe actualizar SAVI a la versión v1\.4\.0 antes del .*noviembre/)
  })

  it('reports download progress', () => {
    const downloading = status({ phase: 'downloading', downloaded_bytes: 455 })
    expect(progressPercent(downloading)).toBe(45)
    expect(progressMessage(downloading)).toBe('Descargando la actualización… 45 %')
    expect(progressPercent(status({ size: null }))).toBeNull()
  })

  it('explains the wait for chat turns', () => {
    expect(progressMessage(status({ phase: 'waiting_turns' }))).toContain('respuestas en curso')
  })
})

describe('restartedWithNewVersion', () => {
  it('detects the restart only when /health answers another version', () => {
    expect(restartedWithNewVersion('v1.4.0', 'v1.3.2')).toBe(true)
    expect(restartedWithNewVersion('v1.3.2', 'v1.3.2')).toBe(false)
    expect(restartedWithNewVersion(null, 'v1.3.2')).toBe(false)
  })
})

describe('installStalled', () => {
  it('waits up to 15 minutes before warning', () => {
    expect(installStalled(null, NOW)).toBe(false)
    expect(installStalled(NOW, NOW + INSTALLING_MAX_MS)).toBe(false)
    expect(installStalled(NOW, NOW + INSTALLING_MAX_MS + 1)).toBe(true)
  })
})

describe('resultNotice', () => {
  const done = { state: 'up_to_date', available_version: null } as const

  it('is a success for an installed update and a warning for anything else', () => {
    const installed = resultNotice(status({ ...done, last_install: installRecord() }), null)
    const failed = resultNotice(
      status({ last_install: installRecord({ outcome: 'rolled_back' }) }),
      null,
    )

    expect(installed).toMatchObject({ tone: 'success', attemptId: 'a1' })
    expect(failed).toMatchObject({ tone: 'warning' })
  })

  it('shows nothing without a record, with updates off, or once seen', () => {
    expect(resultNotice(null, null)).toBeNull()
    expect(resultNotice(status({ last_install: null }), null)).toBeNull()
    expect(resultNotice(status({ enabled: false, last_install: installRecord() }), null)).toBeNull()
    expect(resultNotice(status({ last_install: installRecord() }), 'a1')).toBeNull()
  })

  it('skips a cancellation, an attempt in progress and a failure already on screen', () => {
    expect(
      resultNotice(status({ last_install: installRecord({ outcome: 'cancelled' }) }), null),
    ).toBeNull()
    expect(
      resultNotice(status({ phase: 'downloading', last_install: installRecord() }), null),
    ).toBeNull()
    expect(
      resultNotice(status({ phase: 'failed', last_install: installRecord() }), null),
    ).toBeNull()
  })
})
