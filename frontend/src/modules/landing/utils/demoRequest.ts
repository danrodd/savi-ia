/**
 * Solicitud de demo, sin Vue: se valida y se arma como correo.
 *
 * Todavía no hay un backend público que reciba solicitudes (llegará con SAVI
 * Cloud): el formulario abre el cliente de correo con todo completo.
 */
import { z } from 'zod'

export const demoRequestSchema = z.object({
  name: z.string().trim().min(2, 'Escribe tu nombre.'),
  company: z.string().trim().min(2, 'Escribe el nombre de tu empresa.'),
  email: z.email('Escribe un correo válido.'),
  phone: z.string().trim().max(30).optional().default(''),
  message: z.string().trim().max(1000).optional().default(''),
})

export type DemoRequest = z.input<typeof demoRequestSchema>

export interface DemoValidation {
  ok: boolean
  errors: Partial<Record<keyof DemoRequest, string>>
}

export function validateDemoRequest(request: DemoRequest): DemoValidation {
  const result = demoRequestSchema.safeParse(request)
  if (result.success) return { ok: true, errors: {} }
  const errors: DemoValidation['errors'] = {}
  for (const issue of result.error.issues) {
    const field = issue.path[0] as keyof DemoRequest
    errors[field] ??= issue.message
  }
  return { ok: false, errors }
}

/** `mailto:` con asunto y cuerpo; `null` si no hay destino configurado. */
export function demoMailto(request: DemoRequest, to: string | null): string | null {
  if (!to) return null
  const data = demoRequestSchema.parse(request)
  const lines = [
    `Nombre: ${data.name}`,
    `Empresa: ${data.company}`,
    `Correo: ${data.email}`,
    data.phone ? `Teléfono: ${data.phone}` : null,
    data.message ? `\n${data.message}` : null,
  ].filter((line): line is string => line !== null)
  const subject = `Solicitud de demo de SAVI — ${data.company}`
  return `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join('\n'))}`
}
