# Librerías por Dominio

## Routing y Estado

- **vue-router**: SPA con `createWebHistory`, lazy-loading por ruta (`() => import(...)`), guardias globales (`beforeEach`) para autenticación, MFA y permisos.
- **Pinia**: store oficial con _setup syntax_ — `defineStore('auth', () => { ... })` para mejor inferencia de tipos.

## Data Fetching y Server-State

- **@tanstack/vue-query**: gestión de caché y sincronización.
  - Configuración global: `staleTime: 5 min`, reintentos automáticos.
  - Cada módulo expone composables (`useGetRecurso()`) que envuelven `useQuery`/`useMutation` con **query keys tipadas** (ej. `RECURSO_QUERY_KEY`).
- **axios**: cliente HTTP instanciado UNA sola vez con:
  - Interceptor de request: inyecta `Authorization: Bearer` y `X-Correlation-Id`.
  - Interceptor de response: refresh automático silencioso de tokens con **cola de peticiones fallidas** para evitar condiciones de carrera.
  - Manejo centralizado de 403 (permisos) con redirecciones + notificaciones.
- **Capa de Abstracción HTTP**: envoltorio tipado que añade prefijos globales (`/api`), valida `ApiResponse<T>` y normaliza errores antes de llegar a la UI.

## Tiempo Real

- **@microsoft/signalr / Socket.io**: WebSockets para notificaciones en vivo vía composables (`useRecursoRealtime(userId)`).
  - Conectar en `onMounted`, desconectar en `onUnmounted`.
  - Al recibir eventos: **invalidar query keys de vue-query**, nunca mutar estado local manualmente.

## UI / Diseño

- **Tailwind CSS** (vía Vite plugin): utilidades + variables CSS.
- **shadcn-vue / reka-ui**: primitivas headless y componentes en `src/components/ui/` (no como dependencia).
- **Gestión de Variantes**: `cva` (class-variance-authority) + `clsx` + `tailwind-merge`, expuesto como helper global `cn()`.
- **Animaciones e iconos**: `tw-animate-css` y `lucide-vue-next`.
- **Notificaciones**: `vue-sonner` envuelto en plugin propio con métodos tipados (`$notify.success`, `$notify.error`).

## PWA

- **vite-plugin-pwa + workbox-window**: Service Worker tipo `prompt` (pide confirmación al usuario para actualizar).
- Caché estática de assets. Rutas dinámicas (`/api`, WebSockets) configuradas como `NetworkOnly` explícitamente.

## Helper `cn()`

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```
