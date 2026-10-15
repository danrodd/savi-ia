# Consola de SAVI Cloud

Aplicación web del equipo de SEO Group para administrar clientes, instancias, tokens de
vinculación, alertas, equipo y auditoría. Habla con el API de `cloud/backend`
(`/console/api` y `/console/auth`) desde el mismo origen.

Stack: Vue 3, Pinia, Vue Router, Vite, Vitest, Biome y zod. La interfaz usa el paquete
compartido [`@savi/ui`](../../packages/ui) (tokens, componentes y `useZodForm`): es el mismo
diseño de SAVI. Ver `docs/plataforma/08-ui-compartida-consola.md`.

## Desarrollo

Necesita el API de Cloud corriendo en `:8001` (el `:8000` es el backend de SAVI):

```powershell
# Terminal 1 — API (desde cloud/backend). Para entrar hace falta un usuario del staff:
#   uv run cloud-admin staff create --email vos@empresa.com --name "Tu Nombre" --role admin
$env:CLOUD_ENV = "development"
$env:CLOUD_CONSOLE_SECRET = "una-semilla-de-desarrollo-de-al-menos-32-caracteres"
$env:CLOUD_CONSOLE_COOKIE_SECURE = "false"      # http://localhost no usa HTTPS
$env:CLOUD_DATABASE_URL = "postgresql+asyncpg://usuario:clave@localhost:5432/savi_cloud"
uv run python -m uvicorn app.main:create_app --factory --port 8001

# Terminal 2 — consola. Las dependencias se instalan una sola vez en la raíz del monorepo
# (npm workspaces: SAVI, la consola y packages/ui comparten el lock y el node_modules).
npm install          # desde la raíz del repo
npm run dev          # desde cloud/frontend: http://localhost:5174, con proxy al API
```

## Calidad

```powershell
npm run type-check   # vue-tsc
npm run test:unit    # vitest
npx biome check src
```

## Producción

La imagen de `cloud/backend/Dockerfile` compila la consola y la sirve el mismo proceso del
API (`CLOUD_CONSOLE_STATIC_DIR`). No hay un contenedor aparte. Ver `deploy/master/README.md`.

## Decisiones

- **El access token vive solo en memoria.** El refresh va en una cookie `HttpOnly` +
  `SameSite=Strict`: un XSS no puede robar una sesión de 8 horas. Recargar la página la
  recupera con la cookie.
- **La interfaz oculta, el backend decide.** Los botones dependen de los permisos que informa
  `/console/auth`, pero cada endpoint los vuelve a exigir.
- **Componentes del paquete compartido.** Lo que es solo de la consola (`ConfirmDialog` con
  palabra a escribir, `SecretDialog`, `StatusBadge`, `KpiCard` con definiciones de métricas)
  son composiciones finas sobre `@savi/ui`, no estilos propios.
- **Formularios con zod.** Cada formulario tiene su esquema en `src/lib/schemas/`, espejo de
  las validaciones del backend; los errores 422/400 del servidor vuelven al campo cuando
  corresponde.
- **Pestañas del cliente con URL propia** (`/clientes/:id/ia`, …): se pueden recargar y
  compartir. Los permisos se exigen en toda la cadena de rutas.
- **CSP estricta en producción.** Las fuentes vienen de `@fontsource` (mismo origen) y el
  tema se aplica antes del primer pintado con `public/theme-init.js`, no con un script
  inline.
- **Gráficos en SVG propio** en vez de `echarts`: hoy hay una sola serie de barras y no justifica
  sumar ~1 MB al bundle. Si aparecen más tipos de gráfico, se reevalúa.
