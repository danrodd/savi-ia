# Arquitectura — Estructura Vertical Feature-Based

## Estructura general de `src/`

```
src/
├── main.ts              # Bootstrap: Pinia, Router, vue-query, plugins, validación de env
├── App.vue
├── components/          # Componentes compartidos globales (Modales, Paginación, etc.)
│   └── ui/              # Primitivas autogeneradas (shadcn-vue / reka-ui)
├── composables/         # Hooks transversales (tema, layout, red, breakpoints)
├── config/              # Validación de variables de entorno (zod) y Feature Flags
├── layouts/             # Plantillas maestras (AdminLayout, DashboardLayout, PublicLayout)
├── lib/                 # Utilidades core (HttpClient, formateadores, interceptores)
├── modules/             # ★ NÚCLEO — una carpeta por dominio de negocio
│   ├── auth/
│   ├── permisos/
│   ├── usuarios/
│   ├── facturacion/
│   └── dashboard/
├── plugins/             # Integración de terceros (notificaciones, analíticas)
├── router/              # Configuración global del router y guardias
├── types/               # Interfaces globales (ej. ApiResponse<T>)
└── validation/          # Reglas base y traducciones para Zod
```

## Anatomía de un módulo (ej. `modules/facturacion/`)

```
facturacion/
├── index.ts             # API pública del módulo — re-exports controlados
├── routes.ts            # Definición de rutas inyectables al router global
├── views/               # Páginas completas
├── components/          # Componentes aislados exclusivos de este dominio
├── composables/         # Hooks con lógica de negocio + queries (ej. useGetFacturas)
├── services/            # Clases que interactúan con HttpClient
├── adapters/            # DTOs `*Api` → modelos de dominio
└── types/               # Tipos e interfaces del dominio
```

## Reglas Arquitectónicas Estrictas

1. **Encapsulamiento**: `index.ts` es el contrato público. Otros módulos importan SIEMPRE desde `@/modules/facturacion`, **nunca** desde subcarpetas.
2. **Aislamiento de API**: los `services` NO exponen tipos crudos del protocolo HTTP. Los `adapters` traducen las respuestas del servidor a modelos limpios — un cambio en el backend no debe romper la UI.
3. **Caché Centralizada**: los componentes Vue NUNCA llaman a librerías de fetching directamente. Consumen composables que encapsulan query keys y revalidación.
4. **Unidireccionalidad de Tiempo Real**: los eventos de WebSocket no mutan estado local — emiten comandos de invalidación a la caché de vue-query.

## Seguridad y Comunicación

- **Tokens Seguros**: JWT en cookie `HttpOnly` preferentemente; alternativa: memoria con refresco automático silencioso.
- **Control de Acceso (RBAC/ABAC)**: `modules/permisos` carga la matriz de accesos durante el bootstrap del router. Expone:
  - Utilidad reactiva: `useCan(recurso, accion)`
  - Directiva de plantilla: `v-can="['facturas', 'leer']"`
- **Feature Flags**: configurados en variables de entorno validadas con zod al inicio. La app falla preventivamente si falta configuración crítica.

## Patrones Clave

- Composition API + `<script setup>` universal.
- Pinia con setup syntax (no Options API).
- Separación estricta DTO ↔ Modelo de dominio mediante adapters.
- Imports dinámicos para romper dependencias circulares (ej. entre HttpClient y router al redirigir por auth).
- Code-splitting manual en Vite (`manualChunks` para vendor) + `lazy loading` obligatorio para todas las vistas.
