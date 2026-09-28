/**
 * Textos de la landing, separados del marcado.
 *
 * Regla: solo se promete lo que está validado con pruebas (ver
 * `docs/plataforma/06-landing.md`). Lo que no existe todavía lleva
 * "Próximamente".
 */
import {
  BookOpenText,
  Building2,
  Database,
  FileSearch,
  Globe,
  KeyRound,
  Layers,
  LockKeyhole,
  type LucideIcon,
  MessagesSquare,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-vue-next'

export interface Feature {
  icon: LucideIcon
  title: string
  body: string
  example: string
}

export const FEATURES: Feature[] = [
  {
    icon: Database,
    title: 'Los datos de tu ERP, interpretados',
    body: 'Ventas, clientes y cartera respondidos en lenguaje natural, con cifras reales y sin exportar nada a Excel.',
    example: '¿Cuánto facturamos en marzo frente a febrero?',
  },
  {
    icon: FileSearch,
    title: 'Tus documentos, citados',
    body: 'Políticas, fichas técnicas y escaneos: SAVI los lee, incluso tablas e imágenes, y cita la página exacta.',
    example: '¿Qué descuento puedo dar sin autorización?',
  },
  {
    icon: Globe,
    title: 'Tu sitio web, siempre al día',
    body: 'Precios, horarios y políticas publicados se leen solos y se actualizan de noche. Cada respuesta trae el link.',
    example: '¿Cuántos kilos de equipaje incluye el tiquete?',
  },
  {
    icon: BookOpenText,
    title: 'El ERP explicado',
    body: 'Cómo se hace cada proceso, en qué módulo está y qué pasos seguir, sin buscar en manuales.',
    example: '¿Cómo registro una toma física de inventario?',
  },
]

export interface Step {
  title: string
  body: string
}

export const STEPS: Step[] = [
  {
    title: 'Se instala junto a tu ERP',
    body: 'SAVI corre en un servidor de tu empresa, en tu red. Tus usuarios entran desde el navegador.',
  },
  {
    title: 'Respeta los permisos que ya tienes',
    body: 'Cada persona ve solo lo que el ERP le permite: mismos módulos, mismas empresas, mismos límites.',
  },
  {
    title: 'Responde con fuentes',
    body: 'Cifras del ERP, páginas de documentos y links del sitio web. Si no sabe algo, lo dice.',
  },
]

export interface Pillar {
  icon: LucideIcon
  title: string
  body: string
}

export const SECURITY: Pillar[] = [
  {
    icon: LockKeyhole,
    title: 'Tus datos no salen de tu empresa',
    body: 'La base del ERP nunca se expone a internet ni pasa por servidores de SEO.',
  },
  {
    icon: ShieldCheck,
    title: 'Permisos del ERP, siempre',
    body: 'Un cajero no ve la cartera ni un vendedor el acta de junta. Probado usuario por usuario.',
  },
  {
    icon: Users,
    title: 'Empresas aisladas entre sí',
    body: 'Varias empresas en una instalación sin cruzar un solo dato entre ellas.',
  },
  {
    icon: KeyRound,
    title: 'Consentimiento antes de enviar documentos',
    body: 'Ningún PDF va al proveedor de IA sin que un administrador lo acepte para ese proveedor.',
  },
]

export const VERTICALS = [
  'Agro',
  'Automotriz',
  'Restaurantes',
  'Farmacias',
  'Salud',
  'Bomberos',
  'Microcrédito',
] as const

export interface Plan {
  icon: LucideIcon
  title: string
  badge?: string
  body: string
  points: string[]
}

export const PLANS: Plan[] = [
  {
    icon: KeyRound,
    title: 'Con tu propia clave',
    body: 'Conectas tu cuenta de Claude, OpenAI o Gemini y pagas directamente al proveedor.',
    points: [
      'Eliges el proveedor y el modelo',
      'Consumo visible por usuario y por empresa',
      'Cambias de proveedor cuando quieras',
    ],
  },
  {
    icon: Sparkles,
    title: 'Créditos gestionados por SEO',
    badge: 'Próximamente',
    body: 'Sin cuentas ni claves: SEO pone la IA y tú consumes créditos desde un panel.',
    points: [
      'Un solo proveedor de facturación',
      'Límites y alertas de consumo',
      'Estado de cuenta mensual',
    ],
  },
]

export const HIGHLIGHTS = [
  { icon: MessagesSquare, label: 'Chat en lenguaje natural' },
  { icon: Layers, label: 'Varias empresas, una instalación' },
  { icon: Building2, label: 'Hecho para el ERP de SEO Group' },
] as const
