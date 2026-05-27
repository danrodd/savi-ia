---
name: frontend-shadcn-guide
description: >
  Guía para integrar shadcn-vue dentro de una arquitectura Vue 3 + Tailwind organizada.
  Describe cómo generar componentes, adaptarlos, moverlos a shared/ui y evitar estilos mezclados sin orden.
license: MIT
metadata:
  author: github.com/vuejs-ai
  version: "1.0.0"
  trigger: "Frontend Vue + shadcn-vue"
---

# Frontend Guide: shadcn-vue + Arquitectura Modular

Esta guía muestra cómo usar `shadcn-vue` en un frontend Vue 3 con Tailwind, respetando una arquitectura clara y evitando:
- usar componentes shadcn sin adaptarlos a la app,
- mezclar estilos propios sin orden,
- no integrar los componentes en la arquitectura del proyecto.

## Estructura recomendada

Usa una estructura de carpetas organizada con separación clara entre módulos, UI compartida y utilidades.

```
src/
 ├── modules/
 │   ├── turnos/
 │   ├── vehiculos/
 │   ├── sedes/
 │
 ├── shared/
 │   ├── ui/
 │   │   ├── button/
 │   │   ├── input/
 │   │   ├── card/
 │   │   ├── modal/
 │   │   ├── dialog/
 │   │
 │   ├── components/
 │   │   ├── layout/
 │   │   ├── navbar/
 │   │
 │   ├── composables/
 │   ├── utils/
 │
 ├── router/
 ├── stores/
 ├── assets/
```

### Qué vive en cada capa

- `modules/`: características del dominio. Cada módulo contiene rutas, vistas, componentes específicos y composables de feature.
- `shared/ui/`: componentes de interfaz reutilizables adaptados al sistema de diseño del proyecto.
- `shared/components/`: componentes de composición de layout, barras de navegación, cabeceras, footers.
- `shared/composables/`: lógica reutilizable de Vue y hooks de presentación.
- `shared/utils/`: utilidades de Tailwind, helpers, transformaciones y tipos.

## Pasos para generar componentes shadcn

1. Añade los componentes necesarios desde shadcn-vue:
   - `pnpm dlx shadcn-vue@latest add button`
   - `pnpm dlx shadcn-vue@latest add input`
   - `pnpm dlx shadcn-vue@latest add dialog`

2. Revisa qué archivos generó shadcn-vue.
3. Adapta los componentes generados antes de usarlos directamente.
4. Muévelos a `src/shared/ui/` y renómbralos si hace falta.

## Adaptar shadcn, no usarlo "tal cual"

### Regla 1: no usar shadcn sin adaptarlo

- No copies componentes generados al componente de feature y los dejes como una implementación aislada.
- Extrae los componentes a `shared/ui/` para que el diseño sea coherente en toda la app.
- Adapta los nombres, variantes y tokens a tu sistema de diseño.

### Regla 2: no mezcles estilos propios sin orden

- Usa Tailwind para todo el styling de UI.
- Los estilos personalizados deben vivir en:
  - clases Tailwind utilitarias,
  - `shared/ui/{component}/styles.ts` o `shared/utils/cn.ts` si necesitas una función `cn`.
- Evita CSS en línea y estilos hardcodeados mezclados con clases de shadcn.

### Regla 3: integrarlo a tu arquitectura

- Crea un wrapper para cada componente shadcn dentro de `shared/ui/`.
- Expone únicamente props alineadas con tu dominio y variantes de diseño.
- No uses el componente generado directamente en las vistas del módulo; importa el wrapper de `shared/ui/`.

## Ejemplo de componentes adaptados

### shared/ui/button/Button.vue
- Envolver el componente base de shadcn.
- Exponer variantes: `primary`, `secondary`, `destructive`, `ghost`, `outline`.
- Usar `cn(...)` y `tailwind-merge`.

### shared/ui/input/Input.vue
- Reusar el input de shadcn como base.
- Exponer props comunes: `label`, `error`, `helperText`, `leadingIcon`, `trailingIcon`.
- Adaptar los estilos a las clases globales de la app.

### shared/ui/modal/Modal.vue o dialog/Dialog.vue
- Crear un componente genérico de overlay/dialog.
- Mantener la lógica de apertura/cierre, foco y accesibilidad.
- Permitir slots para encabezado, contenido y acciones.

## Organización del CSS / Tailwind

- Usa Tailwind V4 y el plugin `@tailwindcss/vite` ya instalado.
- Mantén estilos de componentes dentro de clases de utilidad.
- Crea utilitarios comunes en `shared/utils/cn.ts` o `shared/ui/ui-utils.ts`.

### Ejemplo de `cn` utilitario

```ts
import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: Array<string | false | null | undefined>) {
  return twMerge(clsx(inputs))
}
```

### Ejemplo de uso

```vue
<template>
  <button :class="cn("inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition", variantClass, className)">
    <slot />
  </button>
</template>
```

## Cómo estructurar módulos

Cada módulo debe ser dueño de su feature.

- `modules/turnos/`
  - `views/`
  - `components/`
  - `composables/`
  - `turnos.routes.ts`
- `modules/vehiculos/`
- `modules/sedes/`

Los módulos consumen UI compartida desde `shared/ui/` y lógica de `shared/composables/`.

## Integración con router y stores

- Define rutas modulares en `src/router/` y registra módulos en el router principal.
- Usa `src/stores/` para estado global con Pinia.
- Si un módulo necesita estado compartido, expón un store específico y sigue el patrón de feature store.

## Tipos, servicios, composables y adapters

### Tipos

- Define tipos por dominio y por feature.
- Usa `src/shared/types/` para tipos globales y `src/modules/<feature>/types.ts` para tipos específicos del módulo.
- Mantén las interfaces pequeñas y explícitas.

Ejemplo:

```ts
// src/modules/turnos/types.ts
export interface Turno {
  id: string
  fecha: string
  sedeId: string
  vehiculoId: string
  estado: "pendiente" | "confirmado" | "cancelado"
}

export interface TurnoRequest {
  fecha: string
  sedeId: string
  vehiculoId: string
}
```

### Services

- Crea servicios para la comunicación con APIs.
- Usa un adapter de datos cuando la respuesta del backend no coincide con los tipos del frontend.
- Mantén los servicios libres de lógica de UI.

Ejemplo:

```ts
// src/modules/turnos/services/turnos.service.ts
import axios from "axios"
import { Turno, TurnoRequest } from "../types"
import { adaptTurnoFromApi } from "../adapters/turnos.adapter"

const api = axios.create({ baseURL: "/api" })

export const turnosService = {
  async fetchTurnos(): Promise<Turno[]> {
    const { data } = await api.get("/turnos")
    return data.map(adaptTurnoFromApi)
  },

  async createTurno(payload: TurnoRequest): Promise<Turno> {
    const { data } = await api.post("/turnos", payload)
    return adaptTurnoFromApi(data)
  },
}
```

### Adapters

- Traduce la forma de los datos entre API y frontend.
- Centraliza transformaciones de nombres, formatos y tipos.
- Evita lógica de parsing en componentes o composables.

Ejemplo:

```ts
// src/modules/turnos/adapters/turnos.adapter.ts
import type { Turno } from "../types"

export function adaptTurnoFromApi(apiData: any): Turno {
  return {
    id: apiData.id,
    fecha: apiData.fecha,
    sedeId: apiData.sede_id,
    vehiculoId: apiData.vehiculo_id,
    estado: apiData.status,
  }
}
```

### Composables

- Usa composables para encapsular estado y lógica reutilizable de la UI.
- Manténlos independientes de los componentes visuales.
- Usa `useXxx` para efectos, validaciones, llamadas a servicios o gestión de formularios.

Ejemplo:

```ts
// src/modules/turnos/composables/useTurnos.ts
import { ref } from "vue"
import { turnosService } from "../services/turnos.service"
import type { TurnoRequest, Turno } from "../types"

export function useTurnos() {
  const turnos = ref<Turno[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadTurnos() {
    loading.value = true
    error.value = null

    try {
      turnos.value = await turnosService.fetchTurnos()
    } catch (err) {
      error.value = "No se pudieron cargar los turnos"
    } finally {
      loading.value = false
    }
  }

  async function createTurno(payload: TurnoRequest) {
    const nuevo = await turnosService.createTurno(payload)
    turnos.value.push(nuevo)
  }

  return {
    turnos,
    loading,
    error,
    loadTurnos,
    createTurno,
  }
}
```

### Estructura recomendada de carpetas

```
src/modules/turnos/
 ├── adapters/
 │   └── turnos.adapter.ts
 ├── composables/
 │   └── useTurnos.ts
 ├── services/
 │   └── turnos.service.ts
 ├── types.ts
 ├── components/
 ├── views/
 └── turnos.routes.ts
```

## Checklist de revisión

- [ ] Los componentes shadcn se movieron a `shared/ui/`.
- [ ] El código usa Tailwind para clases de estilo.
- [ ] No hay estilos propios dispersos sin orden.
- [ ] Los componentes son wrappers adaptados, no copias directas de shadcn.
- [ ] Los módulos consumen `shared/ui/` y no importan componentes generados directos.
- [ ] Las rutas y stores están organizadas por feature.
- [ ] Los assets están en `src/assets/` y son reutilizables.

## Buenas prácticas específicas

- `shared/ui/button` debe ser el único lugar donde se define la apariencia de botones reutilizables.
- `shared/ui/input` debe mantener el estilo de campos consistente en toda la app.
- `shared/ui/modal` / `shared/ui/dialog` debe controlar la accesibilidad y el comportamiento de overlay.
- `shared/components/layout` debe contener el layout principal de la app.
- `shared/components/navbar` debe contener la navegación y links de módulo.
- Usa `shared/composables/` para hooks de UI compartida, por ejemplo `useDialog()`, `useFormValidation()`, `useToast()`.
- Usa `shared/utils/` para helpers de datos y transformaciones, no para estilos.

## Resultado esperado

Una app frontend Vue organizada donde:
- `shadcn-vue` se usa como base y se adapta a los componentes del sistema,
- los componentes compartidos viven en `shared/ui/`,
- Tailwind controla el estilo de UI,
- la arquitectura feature-based es clara y consistente.
