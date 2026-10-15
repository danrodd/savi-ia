import type { PasswordRule } from '@savi/ui'
import { z } from 'zod'

/** Ingreso con correo y contraseña. */
export const credentialsSchema = z.object({
  email: z.email('Ingresá un correo válido.'),
  password: z.string().min(1, 'Ingresá tu contraseña.'),
})

export const MIN_PASSWORD_LENGTH = 12
export const MAX_PASSWORD_LENGTH = 256

/**
 * Requisitos de la contraseña del staff, espejo de `validate_password_policy` del backend
 * (`cloud/backend/app/modules/staff/security.py`). "No ser una contraseña común" solo lo
 * sabe el servidor: su error llega al confirmar y se muestra en el campo.
 */
export function passwordRules(email: string): PasswordRule[] {
  const local = email.split('@', 1)[0]?.toLowerCase() ?? ''
  const rules: PasswordRule[] = [
    {
      label: `Al menos ${MIN_PASSWORD_LENGTH} caracteres`,
      test: (value) => value.length >= MIN_PASSWORD_LENGTH && value.length <= MAX_PASSWORD_LENGTH,
    },
    {
      label: 'Al menos 5 caracteres distintos',
      test: (value) => new Set(value.toLowerCase()).size >= 5,
    },
  ]
  if (local.length >= 4) {
    rules.push({
      label: 'Que no contenga tu correo',
      test: (value) => value.length > 0 && !value.toLowerCase().includes(local),
    })
  }
  return rules
}

/**
 * Nueva contraseña del primer ingreso: cumple los requisitos y se repite igual. El correo
 * se lee al validar (`getEmail`), así el esquema sigue al correo que se ingresó.
 */
export function newPasswordSchema(getEmail: () => string) {
  return z
    .object({
      password: z.string(),
      repeat: z.string(),
    })
    .superRefine((value, ctx) => {
      const failed = passwordRules(getEmail()).find((rule) => !rule.test(value.password))
      if (failed) {
        ctx.addIssue({
          code: 'custom',
          path: ['password'],
          message: `Falta: ${failed.label.toLowerCase()}.`,
        })
      }
      if (value.repeat !== value.password) {
        ctx.addIssue({ code: 'custom', path: ['repeat'], message: 'Las contraseñas no coinciden.' })
      }
    })
}
