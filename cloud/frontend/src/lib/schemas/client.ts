import { z } from 'zod'

/**
 * Alta y edición de clientes. Espejo de `CreateClientUseCase` y `ClientCreate`/`ClientPatch`
 * del backend: código de 2 a 32 caracteres A-Z, 0-9 o _, nombre obligatorio hasta 200 y NIT
 * opcional hasta 32.
 */

const name = z
  .string()
  .trim()
  .min(1, 'El nombre es obligatorio.')
  .max(200, 'El nombre admite hasta 200 caracteres.')

const nit = z
  .string()
  .trim()
  .max(32, 'El NIT admite hasta 32 caracteres.')
  .transform((value) => value || null)

export const createClientSchema = z.object({
  code: z
    .string()
    .trim()
    .transform((value) => value.toUpperCase())
    .pipe(
      z
        .string()
        .regex(/^[A-Z0-9_]{2,32}$/, 'Entre 2 y 32 caracteres: letras, números o guion bajo.'),
    ),
  name,
  nit,
})

export const editClientSchema = z.object({ name, nit })
