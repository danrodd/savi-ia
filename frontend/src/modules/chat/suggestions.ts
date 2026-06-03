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
  // Contabilidad
  { module: M.CONTABILIDAD, prompt: '¿Cuáles son los saldos contables del mes actual?' },
  { module: M.CONTABILIDAD, prompt: 'Mostrame el balance general del último trimestre.' },
  { module: M.CONTABILIDAD, prompt: '¿Cuál fue el estado de resultados del mes pasado?' },
  { module: M.CONTABILIDAD, prompt: 'Listame los últimos comprobantes contables registrados.' },

  // Nómina
  { module: M.NOMINA, prompt: '¿Cuántos empleados activos hay en la empresa?' },
  { module: M.NOMINA, prompt: 'Mostrame las últimas novedades de nómina registradas.' },
  { module: M.NOMINA, prompt: '¿Qué empleados están próximos a vacaciones?' },

  // Inventario
  { module: M.INVENTARIO, prompt: '¿Qué productos tienen menos de 10 unidades en stock?' },
  { module: M.INVENTARIO, prompt: 'Mostrame los productos con lotes próximos a vencer.' },
  { module: M.INVENTARIO, prompt: '¿Cuál es el valor total del inventario actual?' },
  { module: M.INVENTARIO, prompt: 'Listame los últimos movimientos de inventario.' },

  // Cuentas por cobrar
  { module: M.CUENTACOBRAR, prompt: '¿Cuántas facturas están pendientes de cobro?' },
  { module: M.CUENTACOBRAR, prompt: 'Mostrame las ventas del mes actual.' },
  { module: M.CUENTACOBRAR, prompt: '¿Qué clientes me deben más?' },
  { module: M.CUENTACOBRAR, prompt: 'Listame las facturas emitidas esta semana.' },

  // Cuentas por pagar
  { module: M.CUENTAPAGAR, prompt: '¿Cuáles son las facturas de proveedores próximas a vencer?' },
  { module: M.CUENTAPAGAR, prompt: 'Mostrame las compras del mes actual.' },
  { module: M.CUENTAPAGAR, prompt: '¿Qué órdenes de compra están pendientes?' },

  // Cartera financiera
  { module: M.CARTERAFINANCIERA, prompt: 'Mostrame la edad de cartera de clientes.' },
  { module: M.CARTERAFINANCIERA, prompt: '¿Qué pagos se recibieron esta semana?' },
  { module: M.CARTERAFINANCIERA, prompt: 'Listame las facturas vencidas hace más de 60 días.' },

  // Ventas
  { module: M.VENTA, prompt: '¿Cuál es el resumen de ventas de hoy?' },
  { module: M.VENTA, prompt: 'Mostrame los pedidos pendientes de despachar.' },
  { module: M.VENTA, prompt: '¿Qué cotizaciones siguen activas?' },

  // Activo fijo
  { module: M.ACTIVOFIJO, prompt: 'Listame los activos fijos de la empresa.' },
  { module: M.ACTIVOFIJO, prompt: '¿Cuánta depreciación se calculó este mes?' },

  // Terceros (core)
  { module: M.TERCERO, prompt: 'Buscame un cliente por nombre o NIT.' },
  { module: M.TERCERO, prompt: '¿Qué proveedores están bloqueados?' },

  // Generales — siempre disponibles
  { module: null, prompt: '¿Qué módulos del ERP puedo consultar?' },
  { module: null, prompt: 'Explicame qué cosas podés hacer.' },
  { module: null, prompt: '¿Cómo te puedo sacar el máximo provecho?' },
]
