import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '../App.vue'

describe('App', () => {
  it('renders the router outlet', () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', name: 'stub', component: { template: '<div>stub</div>' } }],
    })
    const wrapper = mount(App, { global: { plugins: [router] } })
    expect(wrapper.exists()).toBe(true)
  })
})
