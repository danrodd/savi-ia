import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import Sidebar from '../Sidebar.vue'

// BrandMark referencia un PNG de `public/` por ruta absoluta, que Vitest no
// resuelve al compilar el componente. No tiene nada que ver con la versión.
vi.mock('../BrandMark.vue', () => ({ default: { template: '<span />' } }))

function mountSidebar(props: { mobile: boolean; open: boolean }) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'home', component: { template: '<div />' } }],
  })
  return mount(Sidebar, {
    props: { conversations: [], activeId: null, loading: false, databaseLabels: null, ...props },
    global: { plugins: [router, createPinia()] },
  })
}

describe('Sidebar — versión de la aplicación', () => {
  it('se ve en el pie sin abrir ningún menú', () => {
    const wrapper = mountSidebar({ mobile: false, open: false })

    const footer = wrapper.find('.sidebar__footer')
    expect(footer.text()).toContain(`SAVI ${__APP_VERSION__}`)
  })

  it('en móvil viaja dentro del cajón: al abrirlo, la versión está', () => {
    const wrapper = mountSidebar({ mobile: true, open: true })

    expect(wrapper.find('.sidebar__footer').text()).toContain(__APP_VERSION__)
  })
})
