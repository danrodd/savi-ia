import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import type { Component } from 'vue'
import DataTableComponent from '../components/DataTable.vue'
import KpiCard from '../components/KpiCard.vue'

const DataTable = DataTableComponent as unknown as Component

let viewport = 1280

function installMatchMedia(): void {
  window.matchMedia = ((query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query)
    return {
      matches: max ? viewport <= Number(max[1]) : false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }
  }) as typeof window.matchMedia
}

afterEach(() => {
  // @ts-expect-error: se retira el simulador para no afectar a otros archivos.
  window.matchMedia = undefined
})

describe('DataTable en tarjetas', () => {
  const columns = [
    { key: 'name', label: 'Nombre', card: 'title' as const },
    { key: 'code', label: 'Código', mono: true },
    { key: 'internal', label: 'Interno', card: 'hidden' as const },
    { key: 'actions', label: '' },
  ]
  const rows = [
    { id: '1', name: 'Farmacias X', code: 'FARMX', internal: 'x' },
    { id: '2', name: 'Cliente Demo', code: 'DEMO', internal: 'y' },
  ]
  const slots = {
    'cell-actions': '<template #cell-actions="{ row }"><i>{{ row.code }}</i></template>',
  }

  it('sin cardsBelow siempre es tabla, aunque la pantalla sea angosta', () => {
    viewport = 320
    installMatchMedia()
    const wrapper = mount(DataTable, { props: { columns, rows, rowKey: 'id' } })

    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.find('[data-test="table-cards"]').exists()).toBe(false)
  })

  it('con cardsBelow, en pantalla ancha sigue siendo tabla', () => {
    viewport = 1280
    installMatchMedia()
    const wrapper = mount(DataTable, { props: { columns, rows, rowKey: 'id', cardsBelow: 720 } })

    expect(wrapper.find('table').exists()).toBe(true)
  })

  it('por debajo del umbral reparte las columnas: título, campos, pie y ocultas', () => {
    viewport = 719
    installMatchMedia()
    const wrapper = mount(DataTable, {
      props: { columns, rows, rowKey: 'id', cardsBelow: 720 },
      slots,
    })
    const card = wrapper.findAll('[data-test="table-card"]')[0]

    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="table-card"]')).toHaveLength(2)
    expect(card?.get('.ui-cards__title').text()).toBe('Farmacias X')
    expect(card?.get('.ui-cards__field dt').text()).toBe('Código')
    expect(card?.findAll('.ui-cards__field')).toHaveLength(1)
    expect(card?.text()).not.toContain('Interno')
    expect(card?.get('.ui-cards__footer').text()).toBe('FARMX') // columna sin etiqueta = pie
  })

  it('el umbral es exclusivo: justo en 720px ya es tabla', () => {
    viewport = 720
    installMatchMedia()
    const wrapper = mount(DataTable, { props: { columns, rows, rowKey: 'id', cardsBelow: 720 } })

    expect(wrapper.find('table').exists()).toBe(true)
  })

  it('clickable: la tarjeta emite row-click con clic y con Enter', async () => {
    viewport = 390
    installMatchMedia()
    const wrapper = mount(DataTable, {
      props: { columns, rows, rowKey: 'id', cardsBelow: 720, clickable: true },
    })
    const first = wrapper.findAll('[data-test="table-card"]')[0]

    await first?.trigger('click')
    await first?.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('row-click')).toEqual([[rows[0]], [rows[0]]])
  })

  it('sin filas muestra el vacío y cargando muestra esqueletos', () => {
    viewport = 390
    installMatchMedia()
    const empty = mount(DataTable, {
      props: { columns, rows: [], rowKey: 'id', cardsBelow: 720, emptyText: 'No hay nada.' },
    })
    expect(empty.text()).toContain('No hay nada.')

    const loading = mount(DataTable, {
      props: { columns, rows: [], rowKey: 'id', cardsBelow: 720, loading: true },
    })
    expect(loading.findAll('.ui-cards__item')).toHaveLength(3)
  })
})

describe('KpiCard alineado', () => {
  it('reserva siempre la línea de contexto, con o sin texto, para que la fila alinee', () => {
    const withHint = mount(KpiCard, { props: { label: 'Costo', value: '1', hint: '0 sin precio' } })
    const without = mount(KpiCard, { props: { label: 'Turnos', value: '2', help: 'Qué es' } })

    expect(withHint.find('.ui-kpi__hint').exists()).toBe(true)
    expect(without.find('.ui-kpi__hint').exists()).toBe(true)
    expect(without.get('.ui-kpi__hint').text()).toBe('')
  })
})
