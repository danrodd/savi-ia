import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '../App.vue'

describe('App', () => {
  it('renders the router outlet', () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', name: 'stub', component: { template: '<div>stub</div>' } }],
    })
    // `App.vue` usa `usePermisosPolling()`, que llama a `usePermisosStore()`
    // en el `setup()`: sin un Pinia activo, `getActivePinia()` revienta antes
    // de que el componente llegue a montarse.
    const wrapper = mount(App, { global: { plugins: [router, createPinia()] } })
    expect(wrapper.exists()).toBe(true)
  })
})
