import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import Alert from '../components/Alert.vue'
import Badge from '../components/Badge.vue'
import Card from '../components/Card.vue'
import DataTableComponent from '../components/DataTable.vue'
import EmptyState from '../components/EmptyState.vue'
import KpiCard from '../components/KpiCard.vue'
import PageHeader from '../components/PageHeader.vue'
import Stepper from '../components/Stepper.vue'
import Tabs from '../components/Tabs.vue'
import UnsavedBar from '../components/UnsavedBar.vue'

describe('Badge, Alert y EmptyState', () => {
  it('el badge aplica el tono', () => {
    const wrapper = mount(Badge, { props: { tone: 'success' }, slots: { default: 'Activo' } })
    expect(wrapper.classes()).toContain('ui-badge--success')
    expect(wrapper.text()).toBe('Activo')
  })

  it('un aviso de peligro se anuncia como alert y los demás como status', () => {
    expect(mount(Alert, { props: { tone: 'danger' } }).attributes('role')).toBe('alert')
    expect(mount(Alert, { props: { tone: 'warning' } }).attributes('role')).toBe('status')
  })

  it('el estado vacío muestra título, descripción y acción', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Sin clientes', description: 'Creá el primero' },
      slots: { default: '<button>Nuevo cliente</button>' },
    })
    expect(wrapper.text()).toContain('Sin clientes')
    expect(wrapper.text()).toContain('Creá el primero')
    expect(wrapper.find('button').exists()).toBe(true)
  })
})

describe('Card, PageHeader y KpiCard', () => {
  it('la tarjeta muestra título, acciones y pie', () => {
    const wrapper = mount(Card, {
      props: { title: 'Suscripción', description: 'Plan y vigencia' },
      slots: { default: 'Cuerpo', actions: '<button>Editar</button>', footer: 'Pie' },
    })
    expect(wrapper.get('h2').text()).toBe('Suscripción')
    expect(wrapper.find('.ui-card__actions button').exists()).toBe(true)
    expect(wrapper.get('footer').text()).toBe('Pie')
  })

  it('el encabezado usa un h1 y muestra las acciones', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Clientes', description: 'Empresas con SAVI' },
      slots: { actions: '<button>Nuevo</button>' },
    })
    expect(wrapper.get('h1').text()).toBe('Clientes')
    expect(wrapper.find('.ui-page-header__actions button').exists()).toBe(true)
  })

  it('el indicador muestra etiqueta, valor y contexto', () => {
    const wrapper = mount(KpiCard, {
      props: { label: 'Turnos', value: '1.204', hint: 'Últimos 30 días' },
    })
    expect(wrapper.text()).toContain('Turnos')
    expect(wrapper.text()).toContain('1.204')
    expect(wrapper.text()).toContain('Últimos 30 días')
  })
})

describe('Stepper', () => {
  it('marca el paso actual y los completados', () => {
    const wrapper = mount(Stepper, {
      props: {
        steps: [
          { key: 'a', label: 'Credenciales' },
          { key: 'b', label: 'Contraseña' },
          { key: 'c', label: 'Segundo factor' },
        ],
        current: 'b',
      },
    })
    const items = wrapper.findAll('li')
    expect(items[0]?.classes()).toContain('ui-stepper__step--done')
    expect(items[1]?.attributes('aria-current')).toBe('step')
    expect(items[2]?.classes()).not.toContain('ui-stepper__step--done')
  })
})

describe('Tabs', () => {
  const items = [
    { key: 'resumen', label: 'Resumen' },
    { key: 'ia', label: 'IA' },
    { key: 'acceso', label: 'Acceso' },
  ]

  it('locales: el clic cambia la pestaña y las flechas recorren', async () => {
    const wrapper = mount(Tabs, {
      props: { items, label: 'Secciones', modelValue: 'resumen' },
      attachTo: document.body,
    })
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs[0]?.attributes('aria-selected')).toBe('true')
    await tabs[1]?.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['ia'])
    await tabs[0]?.trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['acceso'])
    wrapper.unmount()
  })

  it('con `to` son enlaces del router y marca la ruta activa', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/c/resumen', component: { template: '<div />' } },
        { path: '/c/ia', component: { template: '<div />' } },
      ],
    })
    await router.push('/c/ia')
    const wrapper = mount(Tabs, {
      props: {
        label: 'Secciones',
        items: [
          { key: 'resumen', label: 'Resumen', to: '/c/resumen' },
          { key: 'ia', label: 'IA', to: '/c/ia' },
        ],
      },
      global: { plugins: [router] },
    })
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(2)
    expect(links[1]?.classes()).toContain('ui-tabs__tab--active')
    expect(links[0]?.classes()).not.toContain('ui-tabs__tab--active')
  })
})

// Componente genérico: sin alias, `rowKey` se infiere como `never` en el test.
const DataTable = DataTableComponent as unknown as Component

describe('DataTable', () => {
  const columns = [
    { key: 'code', label: 'Código', mono: true },
    { key: 'name', label: 'Nombre' },
  ]
  const rows = [
    { id: '1', code: 'FARMX', name: 'Farmacias X' },
    { id: '2', code: 'DEMO', name: 'Cliente Demo' },
  ]

  it('pinta filas y celdas, con slot por columna', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows, rowKey: 'id' },
      slots: { 'cell-name': '<template #cell-name="{ row }"><b>{{ row.name }}</b></template>' },
    })
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.findAll('th').map((th) => th.text())).toEqual(['Código', 'Nombre'])
    expect(wrapper.find('tbody b').text()).toBe('Farmacias X')
  })

  it('sin filas muestra el texto vacío', () => {
    const wrapper = mount(DataTable, {
      props: { columns, rows: [], rowKey: 'id', emptyText: 'No hay clientes.' },
    })
    expect(wrapper.get('tbody').text()).toBe('No hay clientes.')
  })

  it('cargando y sin datos muestra esqueletos', () => {
    const wrapper = mount(DataTable, { props: { columns, rows: [], rowKey: 'id', loading: true } })
    expect(wrapper.findAll('tbody tr')).toHaveLength(3)
  })

  it('con clickable la fila se activa con clic y con Enter', async () => {
    const wrapper = mount(DataTable, { props: { columns, rows, rowKey: 'id', clickable: true } })
    const first = wrapper.findAll('tbody tr')[0]
    await first?.trigger('click')
    await first?.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('row-click')).toEqual([[rows[0]], [rows[0]]])
    expect(first?.attributes('tabindex')).toBe('0')
  })
})

describe('UnsavedBar', () => {
  it('solo aparece con cambios y emite guardar y descartar', async () => {
    const wrapper = mount(UnsavedBar, { props: { visible: false } })
    expect(wrapper.find('.ui-unsaved').exists()).toBe(false)
    await wrapper.setProps({ visible: true })
    const buttons = wrapper.findAll('button')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    expect(wrapper.emitted('discard')).toHaveLength(1)
    expect(wrapper.emitted('save')).toHaveLength(1)
  })

  it('no deja guardar si el formulario es inválido', async () => {
    const wrapper = mount(UnsavedBar, { props: { visible: true, canSave: false } })
    expect(wrapper.findAll('button')[1]?.attributes('disabled')).toBeDefined()
  })
})
