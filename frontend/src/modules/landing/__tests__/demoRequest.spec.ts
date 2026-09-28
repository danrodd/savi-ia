import { describe, expect, it } from 'vitest'

import { demoMailto, validateDemoRequest } from '../utils/demoRequest'

const valid = {
  name: 'Ana Pérez',
  company: 'Ferretería El Tornillo',
  email: 'ana@tornillo.co',
  phone: '',
  message: 'Tenemos 3 sedes.',
}

describe('validateDemoRequest', () => {
  it('acepta una solicitud completa', () => {
    expect(validateDemoRequest(valid)).toEqual({ ok: true, errors: {} })
  })

  it('marca cada campo obligatorio con su mensaje', () => {
    const result = validateDemoRequest({ ...valid, name: ' ', company: '', email: 'ana@' })

    expect(result.ok).toBe(false)
    expect(Object.keys(result.errors).sort()).toEqual(['company', 'email', 'name'])
  })
})

describe('demoMailto', () => {
  it('arma el correo con asunto y datos', () => {
    const link = demoMailto(valid, 'ventas@seo.test')

    expect(link).toMatch(/^mailto:ventas@seo\.test\?subject=/)
    const body = decodeURIComponent(link?.split('body=')[1] ?? '')
    expect(body).toContain('Empresa: Ferretería El Tornillo')
    expect(body).toContain('Tenemos 3 sedes.')
    expect(body).not.toContain('Teléfono')
  })

  it('sin destino configurado no inventa uno', () => {
    expect(demoMailto(valid, null)).toBeNull()
  })
})
