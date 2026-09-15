import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import Composer from '../Composer.vue'

/**
 * Cuando el backend rechaza un turno por límite de uso (429) o porque la
 * conversación ya tiene una respuesta en curso (409), el rechazo es temporal.
 * Perder lo que el usuario había escrito sería el peor castigo posible, así
 * que el texto vuelve al cuadro.
 */
describe('Composer', () => {
  it('devuelve el texto rechazado al cuadro', async () => {
    const wrapper = mount(Composer, { props: { streaming: false, restoreText: null } })

    await wrapper.setProps({ restoreText: '¿Cuántos empleados hay?' })

    expect(wrapper.find('textarea').element.value).toBe('¿Cuántos empleados hay?')
    expect(wrapper.emitted('restored')).toHaveLength(1)
  })

  it('no pisa lo que el usuario ya volvió a escribir', async () => {
    const wrapper = mount(Composer, { props: { streaming: false, restoreText: null } })
    await wrapper.find('textarea').setValue('otra pregunta')

    await wrapper.setProps({ restoreText: 'la vieja' })

    expect(wrapper.find('textarea').element.value).toBe('otra pregunta')
  })

  it('limpia el cuadro al enviar', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    await wrapper.find('textarea').setValue('hola')

    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('send')?.[0]).toEqual(['hola'])
    expect(wrapper.find('textarea').element.value).toBe('')
  })
})
