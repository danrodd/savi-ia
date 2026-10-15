import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import Checkbox from '../components/Checkbox.vue'
import FormField from '../components/FormField.vue'
import PasswordField from '../components/PasswordField.vue'
import Select from '../components/Select.vue'
import Switch from '../components/Switch.vue'
import Textarea from '../components/Textarea.vue'
import TextField from '../components/TextField.vue'

describe('FormField', () => {
  it('asocia la etiqueta, la ayuda y el error con el control', () => {
    const wrapper = mount(FormField, {
      props: { label: 'Nombre', hint: 'Como figura en la factura', error: 'Obligatorio' },
      slots: { default: (attrs: Record<string, unknown>) => h('input', attrs) },
    })
    const input = wrapper.get('input')
    const id = input.attributes('id')
    expect(wrapper.get('label').attributes('for')).toBe(id)
    expect(input.attributes('aria-invalid')).toBe('true')
    const described = input.attributes('aria-describedby')?.split(' ') ?? []
    expect(described).toHaveLength(2)
    for (const ref of described) expect(wrapper.find(`#${ref}`).exists()).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toBe('Obligatorio')
  })

  it('sin error no marca el control como inválido', () => {
    const wrapper = mount(FormField, {
      props: { label: 'Nombre' },
      slots: { default: (attrs: Record<string, unknown>) => h('input', attrs) },
    })
    expect(wrapper.get('input').attributes('aria-invalid')).toBeUndefined()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})

describe('TextField', () => {
  it('emite el texto escrito', async () => {
    const wrapper = mount(TextField, { props: { label: 'Código', modelValue: '' } })
    await wrapper.get('input').setValue('FARMX')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['FARMX'])
  })

  it('con type="number" emite números y null si queda vacío', async () => {
    const wrapper = mount(TextField, { props: { type: 'number', modelValue: 3 } })
    await wrapper.get('input').setValue('25')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([25])
    await wrapper.get('input').setValue('')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })

  it('avisa el blur para marcar el campo como tocado', async () => {
    const wrapper = mount(TextField, { props: { label: 'Código' } })
    await wrapper.get('input').trigger('blur')
    expect(wrapper.emitted('blur')).toHaveLength(1)
  })
})

describe('Textarea', () => {
  it('emite el texto escrito', async () => {
    const wrapper = mount(Textarea, { props: { label: 'Notas' } })
    await wrapper.get('textarea').setValue('Pago por transferencia')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['Pago por transferencia'])
  })
})

describe('Select', () => {
  const options = [
    { value: 'admin', label: 'Administración' },
    { value: 'soporte', label: 'Soporte' },
  ]

  it('emite el valor de la opción elegida, no su índice', async () => {
    const wrapper = mount(Select, { props: { options, placeholder: 'Elegí un rol' } })
    await wrapper.get('select').setValue('soporte')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['soporte'])
  })

  it('la opción vacía vuelve a null', async () => {
    const wrapper = mount(Select, { props: { options, placeholder: 'Elegí', modelValue: 'admin' } })
    await wrapper.get('select').setValue('')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })

  it('respeta valores numéricos', async () => {
    const wrapper = mount(Select, {
      props: {
        options: [
          { value: 7, label: 'Siete días' },
          { value: 30, label: 'Treinta días' },
        ],
      },
    })
    await wrapper.get('select').setValue('30')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([30])
  })
})

describe('nombre accesible sin etiqueta visible', () => {
  it('el aria-label llega al control, no al contenedor', () => {
    const select = mount(Select, {
      props: { options: [{ value: 'a', label: 'A' }], ariaLabel: 'Rol de Ana' },
    })
    const text = mount(TextField, { props: { ariaLabel: 'Buscar' } })

    expect(select.get('select').attributes('aria-label')).toBe('Rol de Ana')
    expect(text.get('input').attributes('aria-label')).toBe('Buscar')
  })
})

describe('Checkbox y Switch', () => {
  it('el checkbox cambia el modelo', async () => {
    const wrapper = mount(Checkbox, { props: { label: 'Permitir', modelValue: false } })
    await wrapper.get('input').setValue(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([true])
  })

  it('el switch puede tener un nombre propio distinto de la etiqueta visible', () => {
    const wrapper = mount(Switch, { props: { label: 'Activa', ariaLabel: 'Regla Pico de costo' } })
    const button = wrapper.get('[role="switch"]')

    expect(button.attributes('aria-label')).toBe('Regla Pico de costo')
    expect(button.attributes('aria-labelledby')).toBeUndefined()
  })

  it('el switch expone su estado con aria-checked y lo invierte al hacer clic', async () => {
    const wrapper = mount(Switch, { props: { label: 'Bloquear configuración', modelValue: false } })
    const button = wrapper.get('[role="switch"]')
    expect(button.attributes('aria-checked')).toBe('false')
    await button.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([true])
  })
})

describe('PasswordField', () => {
  const rules = [
    { label: 'Al menos 12 caracteres', test: (v: string) => v.length >= 12 },
    { label: 'Al menos 5 caracteres distintos', test: (v: string) => new Set(v).size >= 5 },
  ]

  it('tilda cada requisito a medida que se cumple', async () => {
    const wrapper = mount(PasswordField, {
      props: { label: 'Nueva contraseña', rules, modelValue: 'abcde' },
    })
    const items = wrapper.findAll('li')
    expect(items[0]?.classes()).not.toContain('ui-password__rule--ok')
    expect(items[1]?.classes()).toContain('ui-password__rule--ok')
    await wrapper.setProps({ modelValue: 'abcdefghijkl' })
    expect(wrapper.findAll('li')[0]?.classes()).toContain('ui-password__rule--ok')
  })

  it('el botón muestra y oculta la contraseña', async () => {
    const wrapper = mount(PasswordField, { props: { label: 'Contraseña' } })
    expect(wrapper.get('input').attributes('type')).toBe('password')
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('input').attributes('type')).toBe('text')
    expect(wrapper.get('button').attributes('aria-label')).toBe('Ocultar contraseña')
  })
})
