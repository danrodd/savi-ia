---
name: enterprise-frontend-architecture
description: "Trigger: Vue 3 enterprise frontend, feature-based modules, vue-query, Pinia setup, shadcn-vue, axios HttpClient. Aplica la arquitectura empresarial de referencia."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Carga esta skill cuando se vaya a:

- Crear o auditar un proyecto frontend Vue 3 + Vite + TypeScript de tipo empresarial.
- Definir la estructura `src/modules/` feature-based con `index.ts` como contrato público.
- Configurar `@tanstack/vue-query`, axios con interceptores (auth + refresh), Pinia setup syntax.
- Integrar `shadcn-vue` / `reka-ui`, Tailwind, `cva` + `clsx` + `tailwind-merge` (`cn()`).
- Añadir vee-validate + zod, vue-router con guardias, PWA con `vite-plugin-pwa`.
- Definir capa de servicios con DTO `*Api` vs modelo de dominio vía adapters.
- Tomar decisiones sobre RBAC/ABAC, feature flags, code-splitting, tiempo real (SignalR / Socket.io).

NO la cargues para fixes triviales, refactors locales de una vista, o proyectos no-Vue.

## Hard Rules

- **Encapsulamiento por módulo**: importar SIEMPRE desde `@/modules/<dominio>`, nunca desde subcarpetas internas. El `index.ts` es el único contrato público.
- **DTO ≠ Modelo**: los servicios devuelven modelos de dominio; los DTOs crudos (`*Api`) NO escapan de la capa de adapters.
- **Caché centralizada**: los componentes NUNCA llaman axios/HttpClient directo. Consumen composables (`useGet*`, `useCreate*`) que envuelven `useQuery`/`useMutation` con query keys tipadas.
- **Tiempo real unidireccional**: los WebSockets NO mutan estado local — invalidan cachés de vue-query.
- **Variables de entorno validadas**: validá `import.meta.env` al bootstrap con zod; la app debe romperse temprano si falta una env crítica.
- **Tokens**: JWT en cookie `HttpOnly` (preferible) o en memoria con refresh automático y cola anti-condición de carrera.
- **Pinia setup syntax**: `defineStore('x', () => { ... })`. Nunca options API.
- **`<script setup>` + Composition API** universal. Sin Options API en código nuevo.
- **Lazy-loading obligatorio** de todas las vistas en `vue-router` y `manualChunks` para vendor en Vite.
- **Tests co-localizados**: `Archivo.ts` junto a `Archivo.spec.ts`.

## Decision Gates

| Decisión | Acción |
|----------|--------|
| ¿Nuevo dominio de negocio? | Crear carpeta en `src/modules/<dominio>/` con la anatomía de [references/architecture.md](references/architecture.md) y exponer `index.ts` |
| ¿Consumir nuevo endpoint? | Servicio en `modules/<x>/services/` usando HttpClient tipado + adapter |
| ¿La API difiere del modelo UI? | Crear `adapters/<entidad>.adapter.ts` (función pura) |
| ¿Evento de WebSocket recibido? | Invalidar query keys, NUNCA mutar estado local manualmente |
| ¿Componente UI shared o de dominio? | Si es reutilizable y agnóstico → `src/components/ui/` (shadcn). Si es del dominio → `modules/<x>/components/` |
| ¿Lógica de validación de formulario? | `vee-validate` + `zod` con error map global ([references/forms-and-validation.md](references/forms-and-validation.md)) |
| ¿Necesitás permisos en UI? | `useCan(recurso, accion)` o directiva `v-can` desde `modules/permisos` |

## Execution Steps

1. Antes de tocar código, leé las references relevantes según el cambio (ver tabla de gates).
2. Si es un proyecto nuevo, ejecutá el starter en [assets/starter-kit.sh](assets/starter-kit.sh) y validá `package.json` engines (Node >=20).
3. Para cada cambio, verificá que respete las Hard Rules — si rompés una, justificá en el PR.
4. Reportá decisiones arquitectónicas no triviales vía `mem_save` (engram) con `type: architecture`.

## Output Contract

Cuando apliques esta skill, entregá:

- Cambios alineados con la estructura `modules/` feature-based.
- Servicios + adapters + composables + tipos co-localizados por módulo.
- Tests `.spec.ts` co-localizados con el archivo bajo prueba.
- Imports siempre desde `@/modules/<x>` (nunca rutas internas).
- Si introducís una dependencia nueva, justificá por qué no alcanzaba la del stack base.

## References

- [references/stack.md](references/stack.md) — Stack base, versiones, runtime.
- [references/libraries.md](references/libraries.md) — Librerías por dominio (vue-query, axios, signalr, ui, formularios, PWA).
- [references/architecture.md](references/architecture.md) — Estructura `src/`, anatomía de módulo, reglas estrictas, seguridad.
- [references/testing-and-tooling.md](references/testing-and-tooling.md) — Vitest, Playwright, oxlint+ESLint+Prettier, code-splitting.
- [references/forms-and-validation.md](references/forms-and-validation.md) — vee-validate + zod, error map i18n.
- [assets/starter-kit.sh](assets/starter-kit.sh) — Comandos pnpm para bootstrap.
