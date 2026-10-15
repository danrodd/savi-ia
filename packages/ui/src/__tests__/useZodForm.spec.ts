import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { z } from 'zod'
import { useZodForm } from '../composables/useZodForm'

const schema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio.'),
  users: z.number().int().min(1, 'Al menos 1 usuario.'),
})

describe('useZodForm', () => {
  it('no muestra errores hasta tocar el campo', () => {
    const form = useZodForm(schema, { name: '', users: 1 })
    expect(form.isValid.value).toBe(false)
    expect(form.errors.value.name).toBeUndefined()
    form.touch('name')
    expect(form.errors.value.name).toBe('El nombre es obligatorio.')
  })

  it('al intentar enviar muestra todos los errores y no ejecuta la acción', async () => {
    const form = useZodForm(schema, { name: '', users: 0 })
    const action = vi.fn()
    expect(await form.handleSubmit(action)).toBe(false)
    expect(action).not.toHaveBeenCalled()
    expect(form.errors.value).toEqual({
      name: 'El nombre es obligatorio.',
      users: 'Al menos 1 usuario.',
    })
  })

  it('con datos válidos ejecuta la acción con la salida del esquema', async () => {
    const form = useZodForm(schema, { name: '  Pro  ', users: 3 })
    const action = vi.fn()
    expect(await form.handleSubmit(action)).toBe(true)
    expect(action).toHaveBeenCalledWith({ name: 'Pro', users: 3 })
  })

  it('isDirty compara contra el último estado guardado', () => {
    const form = useZodForm(schema, { name: 'A', users: 1 })
    expect(form.isDirty.value).toBe(false)
    form.values.name = 'B'
    expect(form.isDirty.value).toBe(true)
    form.reset({ name: 'B', users: 1 })
    expect(form.isDirty.value).toBe(false)
    form.values.users = 4
    form.reset()
    expect(form.values.users).toBe(1)
  })

  it('los errores del servidor se muestran y se borran al editar', async () => {
    const form = useZodForm(schema, { name: 'A', users: 1 })
    form.setServerErrors({ name: 'Ya existe un cliente con ese nombre.' })
    expect(form.errors.value.name).toBe('Ya existe un cliente con ese nombre.')
    form.values.name = 'B'
    await nextTick()
    expect(form.errors.value.name).toBeUndefined()
  })

  it('submitting está activo mientras corre la acción', async () => {
    const form = useZodForm(schema, { name: 'A', users: 1 })
    let release: () => void = () => undefined
    const pending = form.handleSubmit(() => new Promise<void>((r) => (release = r)))
    expect(form.submitting.value).toBe(true)
    release()
    await pending
    expect(form.submitting.value).toBe(false)
  })
})
