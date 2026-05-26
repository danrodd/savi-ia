import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from '../App.vue'

describe('App', () => {
  it('renders the SAVI welcome view', () => {
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('SAVI')
    expect(wrapper.text()).toContain('Sistema de Asistente Virtual Inteligente')
  })
})
