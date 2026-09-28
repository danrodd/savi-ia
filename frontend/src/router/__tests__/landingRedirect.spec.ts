import { describe, expect, it } from 'vitest'

import { shouldShowLanding } from '../landingRedirect'

describe('shouldShowLanding', () => {
  it('lleva a la landing a quien entra a la raíz sin sesión', () => {
    expect(shouldShowLanding('home', false, true)).toBe(true)
  })

  it('con sesión, la raíz sigue siendo el chat', () => {
    expect(shouldShowLanding('home', true, true)).toBe(false)
  })

  it('con la landing apagada (servidor de un cliente), la raíz lleva al login', () => {
    expect(shouldShowLanding('home', false, false)).toBe(false)
  })

  it('un link a una conversación sin sesión sigue yendo al login', () => {
    expect(shouldShowLanding('conversation', false, true)).toBe(false)
  })
})
