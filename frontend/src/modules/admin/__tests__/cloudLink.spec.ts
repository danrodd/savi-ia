import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CloudLinkState } from '../types'
import {
  cloudLinkErrorMessage,
  globalAlertText,
  needsGlobalAlert,
  statusTone,
  streamProgress,
} from '../utils/cloudLink'

const serviceMock = vi.hoisted(() => ({
  status: vi.fn(),
  link: vi.fn(),
  unlink: vi.fn(),
  syncNow: vi.fn(),
  preview: vi.fn(),
}))
vi.mock('../services/cloudLinkService', () => ({ cloudLinkService: serviceMock }))

import CloudPreviewPanel from '../components/CloudPreviewPanel.vue'
import { useCloudLinkStore } from '../stores/cloudLinkStore'

const NOW = new Date('2026-10-14T12:00:00Z')

function state(over: Partial<CloudLinkState> = {}): CloudLinkState {
  return {
    status: 'linked',
    cloud_configured: true,
    sync_enabled: true,
    client_code: 'ACME',
    client_name: 'Acme SAS',
    instance_id: '11111111-1111-1111-1111-111111111111',
    linked_at: '2026-10-01T10:00:00Z',
    last_heartbeat_ok_at: '2026-10-14T11:55:00Z',
    last_attempt_at: '2026-10-14T11:55:00Z',
    last_error_code: null,
    streams: [],
    notices: [],
    ...over,
  }
}

function httpError(status: number, errorCode: string | undefined, message: string) {
  return Object.assign(new Error(message), { status, body: errorCode ? { errorCode } : {} })
}

describe('statusTone', () => {
  it('verde conectada, ámbar sin conexión, rojo el resto', () => {
    expect(statusTone('linked')).toBe('ok')
    expect(statusTone('offline')).toBe('warn')
    expect(statusTone('suspended')).toBe('danger')
    expect(statusTone('unauthorized')).toBe('danger')
    expect(statusTone('revoked')).toBe('danger')
  })
})

describe('needsGlobalAlert', () => {
  it('no avisa sin estado, vinculada ni sin vincular', () => {
    expect(needsGlobalAlert(null, NOW)).toBe(false)
    expect(needsGlobalAlert(state(), NOW)).toBe(false)
    expect(needsGlobalAlert(state({ status: 'unlinked' }), NOW)).toBe(false)
  })

  it('offline avisa solo a partir de 72 horas', () => {
    const recent = state({ status: 'offline', last_heartbeat_ok_at: '2026-10-12T13:00:00Z' })
    const old = state({ status: 'offline', last_heartbeat_ok_at: '2026-10-11T11:00:00Z' })

    expect(needsGlobalAlert(recent, NOW)).toBe(false)
    expect(needsGlobalAlert(old, NOW)).toBe(true)
    expect(globalAlertText(old)).toContain('72 horas')
  })

  it('offline sin heartbeat usa la fecha de vinculación', () => {
    const s = state({
      status: 'offline',
      last_heartbeat_ok_at: null,
      linked_at: '2026-10-01T00:00:00Z',
    })

    expect(needsGlobalAlert(s, NOW)).toBe(true)
  })

  it.each(['suspended', 'unauthorized', 'revoked'] as const)('%s avisa siempre', (status) => {
    expect(needsGlobalAlert(state({ status }), NOW)).toBe(true)
  })
})

describe('cloudLinkErrorMessage', () => {
  it('mapea el errorCode del backend', () => {
    expect(cloudLinkErrorMessage(httpError(404, 'enrollment_token_invalid', 'x'))).toContain(
      'no existe',
    )
    expect(cloudLinkErrorMessage(httpError(403, 'client_suspended', 'x'))).toContain('suspendida')
    expect(cloudLinkErrorMessage(httpError(429, 'too_many_requests', 'x'))).toContain('intentos')
  })

  it('reconoce "ya vinculada" (422) y usa el mensaje como último recurso', () => {
    expect(
      cloudLinkErrorMessage(httpError(422, undefined, 'Esta instalación ya está vinculada.')),
    ).toContain('Desvinculala')
    expect(cloudLinkErrorMessage(httpError(400, undefined, 'Algo raro'))).toBe('Algo raro')
  })
})

describe('streamProgress', () => {
  it('al día si el watermark es reciente; enviando historial si no hay envío o va atrasado', () => {
    expect(
      streamProgress(
        { last_ok_at: '2026-10-14T11:00:00Z', watermark_at: '2026-10-14T10:00:00Z' },
        NOW,
      ),
    ).toBe('al día')
    expect(streamProgress({ last_ok_at: null, watermark_at: '2026-10-14T10:00:00Z' }, NOW)).toBe(
      'enviando historial…',
    )
    expect(
      streamProgress(
        { last_ok_at: '2026-10-14T11:00:00Z', watermark_at: '2026-09-01T00:00:00Z' },
        NOW,
      ),
    ).toBe('enviando historial…')
  })
})

describe('cloudLinkStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('carga el estado', async () => {
    serviceMock.status.mockResolvedValue(state())
    const store = useCloudLinkStore()

    await store.load()

    expect(store.state?.client_name).toBe('Acme SAS')
    expect(store.isLinked).toBe(true)
  })

  it('vincular guarda el estado y traduce los errores', async () => {
    const store = useCloudLinkStore()
    serviceMock.link.mockResolvedValueOnce(state())

    await store.link('  svk_enr_abc ', 'from_now')

    expect(serviceMock.link).toHaveBeenCalledWith('svk_enr_abc', 'from_now')
    expect(store.isLinked).toBe(true)

    serviceMock.link.mockRejectedValueOnce(httpError(404, 'enrollment_token_invalid', 'x'))
    await expect(store.link('svk_enr_x', 'all')).rejects.toThrow('no existe')
  })

  it('desvincular recarga el estado', async () => {
    serviceMock.unlink.mockResolvedValue(undefined)
    serviceMock.status.mockResolvedValue(state({ status: 'unlinked', client_name: null }))
    const store = useCloudLinkStore()

    await store.unlink()

    expect(serviceMock.unlink).toHaveBeenCalled()
    expect(store.isLinked).toBe(false)
  })

  it('el aviso global sale del estado cargado', async () => {
    serviceMock.status.mockResolvedValue(state({ status: 'revoked' }))
    const store = useCloudLinkStore()

    await store.load()

    expect(store.showGlobalAlert).toBe(true)
  })
})

describe('CloudPreviewPanel', () => {
  it('muestra el JSON, la explicación y lo que no se envía', () => {
    const wrapper = mount(CloudPreviewPanel, {
      props: {
        loading: false,
        error: null,
        preview: {
          heartbeat: { version: '1.2.3' },
          events: { turn: { model: 'sonnet' }, session: null },
        },
      },
    })

    expect(wrapper.get('[data-testid="cloud-preview-heartbeat"]').text()).toContain(
      '"version": "1.2.3"',
    )
    expect(wrapper.text()).toContain('Respuestas de SAVI')
    expect(wrapper.text()).toContain('nada pendiente')
    expect(wrapper.get('[data-testid="cloud-not-sent"]').text()).toContain('consultas SQL')
  })

  it('sin vista previa igual aclara lo que nunca se envía', async () => {
    const wrapper = mount(CloudPreviewPanel, {
      props: { loading: false, error: null, preview: null },
    })

    expect(wrapper.find('[data-testid="cloud-preview-heartbeat"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="cloud-not-sent"]').text()).toContain('nombres de usuario')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('load')).toHaveLength(1)
  })
})
