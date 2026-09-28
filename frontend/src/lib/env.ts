function required(name: string, value: string | undefined): string {
  if (!value || value.trim() === '') {
    throw new Error(`Missing required env var: ${name}`)
  }
  return value
}

function optional(value: string | undefined): string | null {
  return value && value.trim() !== '' ? value.trim() : null
}

export const ENV = {
  API_BASE_URL: required('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL),
  /**
   * Landing pública en `/inicio`. Apagada por defecto: el mismo frontend se
   * instala en el servidor de cada empresa, y ahí no tiene sentido.
   */
  LANDING_ENABLED: import.meta.env.VITE_LANDING_ENABLED === 'true',
  /** Destino de "Solicitar demo". Sin él, el formulario avisa que falta. */
  LANDING_CONTACT_EMAIL: optional(import.meta.env.VITE_LANDING_CONTACT_EMAIL),
} as const
