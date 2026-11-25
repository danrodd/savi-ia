/**
 * Sugerencias de preguntas por módulo del ERP.
 *
 * Las usa la pantalla de bienvenida para mostrar pines clickeables que
 * el usuario puede disparar como primer mensaje. El catálogo es estático
 * y curado — no lo genera el LLM.
 *
 * Reglas:
 * - Cada entrada vive bajo el `ModuleCode` al que pertenece.
 * - Las preguntas son naturales, en primera persona, como las haría el
 *   usuario al chat.
 * - GENERAL no requiere módulo específico — son las que ven los usuarios
 *   sin verticales o cuando hay pocas opciones.
 * - Solo preguntas que el catálogo de datos responde (ventas, compras,
 *   cartera, terceros, inventario, anticipos y devoluciones). Una sugerencia
 *   fuera del catálogo (nómina, contabilidad general, activos fijos) promete
 *   algo que SAVI solo puede intentar por SQL libre.
 */
import { M, type ModuleCode } from '@/modules/permisos'

export interface ChatSuggestion {
  /** Etiqueta corta para el chip del módulo. Si es null, no se muestra. */
  module: ModuleCode | null
  /** Texto que se envía como mensaje al hacer click. */
  prompt: string
  /** Texto corto que se renderiza en la card. Default: prompt. */
  label?: string
}

export const SUGGESTIONS: ChatSuggestion[] = [
  // Contabilidad (los anticipos los ve también este módulo)
  { module: M.CONTABILIDAD, prompt: '¿Qué anticipos de clientes siguen pendientes por cruzar?' },
  { module: M.CONTABILIDAD, prompt: '¿Qué anticipos a proveedores siguen sin cruzar?' },

  // Inventario
  { module: M.INVENTARIO, prompt: '¿Qué productos tienen menos de 10 unidades en stock?' },
  { module: M.INVENTARIO, prompt: '¿Qué productos están por debajo del mínimo?' },
  { module: M.INVENTARIO, prompt: '¿Qué productos llevan más de un año sin venderse?' },

  // Cuentas por cobrar
  { module: M.CUENTACOBRAR, prompt: '¿Cuántas facturas están pendientes de cobro?' },
  { module: M.CUENTACOBRAR, prompt: 'Muéstreme las ventas del mes actual.' },
  { module: M.CUENTACOBRAR, prompt: '¿Qué clientes me deben más?' },
  { module: M.CUENTACOBRAR, prompt: 'Lísteme las facturas emitidas esta semana.' },

  // Cuentas por pagar
  { module: M.CUENTAPAGAR, prompt: '¿Cuáles son las facturas de proveedores próximas a vencer?' },
  { module: M.CUENTAPAGAR, prompt: 'Muéstreme las compras del mes actual con el IVA por tarifa.' },
  { module: M.CUENTAPAGAR, prompt: '¿Qué devoluciones a proveedores se hicieron este mes?' },
  { module: M.CUENTAPAGAR, prompt: '¿Cuánto tenemos vencido por pagar a proveedores?' },

  // La cartera de clientes la ven Cuentas por cobrar y Ventas; Cartera
  // financiera es otro módulo del ERP y no está en el catálogo.
  { module: M.CUENTACOBRAR, prompt: 'Muéstreme la edad de cartera de clientes.' },
  { module: M.CUENTACOBRAR, prompt: 'Lísteme las facturas vencidas hace más de 60 días.' },

  // Ventas
  { module: M.VENTA, prompt: '¿Cuál es el resumen de ventas de hoy?' },
  { module: M.VENTA, prompt: '¿Cuánto vendió cada vendedor este mes?' },
  { module: M.VENTA, prompt: '¿Cuánto se devolvió en ventas este mes?' },

  // Terceros (core)
  { module: M.TERCERO, prompt: 'Búsqueme un cliente por nombre o NIT.' },
  { module: M.TERCERO, prompt: '¿Qué proveedores están bloqueados?' },

  // Generales — siempre disponibles
  { module: null, prompt: '¿Qué módulos del ERP puedo consultar?' },
  { module: null, prompt: 'Explíqueme qué cosas puede hacer.' },
  { module: null, prompt: '¿Cómo puedo sacarle el máximo provecho a SAVI?' },
]
