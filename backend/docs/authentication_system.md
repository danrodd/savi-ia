# Sistema de Autenticación y Autorización de SAVI

Este documento describe **cómo SAVI sabe quién sos y qué módulos del ERP podés ver**. Está pensado para que cualquier persona del equipo entienda el flujo de extremo a extremo sin tener que leer el código.

> **Resumen ejecutivo**: la identidad la valida la base de datos del ERP (esquema `Seguridad`). Una vez autenticado, SAVI calcula a qué módulos del ERP tenés acceso combinando tres fuentes: el flag de administrador, el plan contratado por el cliente, y los permisos por formulario asignados al usuario. Ese set de módulos se entrega al frontend en un endpoint de "bootstrap" y se cachea con un hash de versión para detectar cambios en caliente.

---

## 1. Identidad: quién sos

La identidad la sigue manejando el ERP. SAVI **no crea usuarios propios**: reutiliza la tabla `Seguridad.Usuario` del cliente.

- El login pide `usuario` y `contraseña`. El backend hashea con MD5 (heredado del ERP) y compara contra `Seguridad.Usuario.clave`.
- Si las credenciales matchean y el usuario está activo (`estado = true`), SAVI emite un par de tokens JWT propio: un **access token** corto (15 min) y un **refresh token** largo (7 días, rotativo).
- El access token contiene solo lo mínimo: `idUsuario`, `login`, `nombre completo`, `is_admin`, `purpose: access`. **NO contiene la lista de módulos** — eso vive en el endpoint de bootstrap (ver sección 3).
- Al hacer refresh, los tokens se rotan (se revoca el anterior, se emite uno nuevo) y se re-leen los datos del usuario desde el ERP. Eso permite que cambios de nombre, deshabilitación, o conversión a admin se reflejen en la siguiente ventana sin reloguear.

## 2. Autorización: a qué módulos accedés

SAVI gating funciona a **nivel módulo**, no a nivel acción. No nos interesa por ahora distinguir entre "puede crear factura" y "puede consultar factura"; nos interesa decir "tiene acceso a Contabilidad" o "no lo tiene".

El cálculo de módulos accesibles es una composición de tres reglas que se aplican en orden:

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Bypass de administrador                                   │
│    Si Usuario.administrador = true → todos los módulos.      │
└──────────────────────────────────────────────────────────────┘
                            │ (no es admin)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Permisos del usuario (granularidad mínima del ERP)        │
│    Se buscan los módulos donde el usuario tiene al menos     │
│    UN permiso activo en algún formulario activo.             │
│    Fuente: Seguridad.PermisoFormulario × Seguridad.Formulario│
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Plan contratado por el cliente                            │
│    Para módulos VERTICALES (Contabilidad, Nómina, Inventario,│
│    etc.), el flag correspondiente en SEO.Modulo debe estar   │
│    en true. Si el plan no lo cubre, se descarta aunque el    │
│    usuario tenga permisos individuales.                      │
│    Para módulos CORE (Seguridad, Tercero, General, Empresa,  │
│    Búsqueda) no se aplica este filtro — son siempre del      │
│    sistema.                                                  │
│    El módulo HERRAMIENTA queda RESERVADO a administradores.  │
└──────────────────────────────────────────────────────────────┘
```

### Decisiones de mapeo confirmadas con el equipo del ERP

Estas reglas no son derivables solo desde la BD — las acordamos con el director de desarrollo y se materializan como constantes en el código:

| Decisión | Regla |
|---|---|
| Fila vigente de `SEO.Modulo` | La de mayor `idModulo` (la más reciente del sync del portal SEO). |
| Módulo VENTA | No tiene flag propio en `SEO.Modulo`. Queda atado al flag `cuentaCobrar`: si el cliente contrató cuentas por cobrar, accede a VENTA. |
| Módulo HERRAMIENTA | Reservado a administradores, independientemente del plan o de los permisos individuales. |
| Módulos CORE | SEGURIDAD, TERCERO, EMPRESA, GENERAL, BÚSQUEDA. Siempre disponibles para cualquier usuario con al menos un permiso en ese módulo. No se filtran por plan. |

## 3. Bootstrap: cómo se entrega al frontend

El frontend no calcula permisos — los pide. Después de autenticarse, llama a un endpoint dedicado:

```
GET /auth/me/bootstrap
Authorization: Bearer <access_token>

Response:
{
  "user": {
    "id": 397,
    "login": "FSCOGL02",
    "full_name": "...",
    "is_admin": false
  },
  "modules": ["CONTABILIDAD", "CUENTAPAGAR", "TERCERO", "GENERAL"],
  "version": "a3f5b2c1..."
}
```

- **`modules`** es la fuente de verdad para la UI: qué vistas mostrar, qué botones habilitar, qué consultas tiene sentido pedirle a SAVI.
- **`version`** es un hash SHA-256 estable del set efectivo (`user_id + sorted(modules)`). El frontend lo guarda y lo compara periódicamente.

### Por qué no embebimos los módulos en el JWT

Lo decidimos así a propósito:

- Si los embebemos, el token crece y el cliente paga ese costo en cada request.
- Si cambia el plan del cliente (nuevo módulo contratado) o se asigna un permiso nuevo a media sesión, **el cambio no se reflejaría hasta el próximo refresh del token** — hasta 15 minutos de delay.
- Con el endpoint de bootstrap + version polling (siguiente sección), el delay máximo baja a la ventana de polling.

El JWT se queda solo con identidad. La autorización es información viva que se consulta.

## 4. Refresco automático del estado

El estado de permisos puede cambiar sin que el usuario haga nada (un admin le quitó un permiso, el cliente upgradeó el plan). El frontend se entera de tres formas automáticas:

```
┌───────────────────────────────────────────────────────────────┐
│ A. Polling silencioso de versión                              │
│    Cada 5 minutos el frontend pide                            │
│    GET /auth/me/modules-version                               │
│    Si el hash cambió → recarga el bootstrap completo.         │
│    Si la pestaña pasa de background a foreground → check      │
│    inmediato (no espera al próximo tick).                     │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│ B. Reload forzado por 403                                     │
│    Si un endpoint protegido devuelve 403 con                  │
│    errorCode: "module_access_denied", el HttpClient asume     │
│    que el caché está stale y dispara un cargarBootstrap().    │
│    La siguiente operación trabajará con el set actualizado.   │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│ C. Refresh por rotación de tokens                             │
│    Al rotar el refresh token también se recalcula y se        │
│    cachea el is_admin del JWT. Esto cubre el caso de que un   │
│    admin pierda el flag administrador durante la sesión.      │
└───────────────────────────────────────────────────────────────┘
```

## 5. Vista del backend

Las piezas que viven en el backend, sin entrar en código:

- **Módulo `auth.domain`**: tipos puros — `ModuleCode` (enum con los 16 módulos del ERP), `AuthenticatedUser` (incluye `modules`), clasificación de módulos (`CORE_MODULES`, `ADMIN_ONLY_MODULES`, `MODULE_TO_SEO_FLAG`).
- **Módulo `auth.application`**: caso de uso `ResolveUserModules` que aplica las tres reglas. Es donde vive la lógica de negocio de autorización. Es testeable sin tocar BD usando repositorios fake.
- **Módulo `auth.infrastructure`**:
  - Repositorios de lectura sobre el ERP: uno para `SEO.Modulo` (el plan vigente), otro para `Seguridad.PermisoFormulario × Seguridad.Formulario` (los módulos donde el usuario tiene al menos un permiso activo).
  - Endpoints HTTP: `/auth/me/bootstrap` y `/auth/me/modules-version`.
  - Dependencia FastAPI `RequireModule(code)` para proteger endpoints futuros que requieran un módulo específico (devuelve 403 con `module_access_denied` cuando el usuario no lo tiene).

## 6. Vista del frontend

El frontend tiene un módulo dedicado a permisos, totalmente separado del módulo de auth:

- **`modules/permisos/constants.ts`**: el set `M` con los 16 códigos de módulo. **Es espejo manual del backend** — cualquier cambio se replica a mano. La fricción es deliberada: fuerza la sincronización.
- **`modules/permisos/stores/permisosStore.ts`**: store de Pinia con `modules: Set<string>`, `version: string | null`, `isAdmin: boolean` y un método `puede(M.X)` que retorna `false` si el bootstrap aún no cargó (fail-closed).
- **`composables/useModule(code)`**: el hook estándar. Devuelve un `ComputedRef<boolean>` que se reevalúa solo si cambia el set.
- **`composables/usePermisosPolling`**: lanza el polling de version cada 5 minutos y reacciona a cambios de visibilidad de la pestaña.
- **`directives/v-module`**: directiva para gating inline en templates. `v-module="M.CONTABILIDAD"` oculta el elemento; `v-module:disabled="M.CONTABILIDAD"` lo deshabilita sin ocultarlo.
- **Router guard global**: las rutas declaran `meta.requireModule: 'CONTABILIDAD'`. Si el usuario no lo tiene, el guard redirige a una vista de "sin acceso" (no a login — la sesión es válida, simplemente no tiene acceso al recurso).
- **Vista de perfil**: muestra los módulos habilitados como chips. Para que el usuario sepa con qué cuenta y qué le falta.

## 7. Ciclo de vida completo, paso a paso

```
1. Usuario abre /login → ingresa credenciales.
2. POST /auth/login → backend valida contra ERP.
3. Si OK → backend emite { access, refresh } y los persiste en localStorage.
4. Frontend dispara GET /auth/me/bootstrap.
5. Backend resuelve módulos (admin? permisos? plan?) → devuelve { user, modules, version }.
6. permisosStore guarda el set y la version. Arranca usePermisosPolling.
7. Router navega a /. El guard ya tiene el bootstrap → renderiza la app.
8. Cada 5 min (o al volver de background): GET /auth/me/modules-version.
   - Si version cambió → recarga bootstrap, UI se actualiza reactivamente.
   - Si no cambió → no hace nada.
9. Si un endpoint backend devuelve 403 con module_access_denied:
   - HttpClient dispara cargarBootstrap() en paralelo al error.
   - El usuario ve el error de esa operación pero el siguiente intento ya está al día.
10. Al expirar el access token (15 min) → refresh transparente vía interceptor.
11. Al hacer logout → backend revoca el refresh, frontend limpia store y localStorage.
```

## 8. Reglas críticas (no negociables)

1. **El frontend no decide autorización — la consulta y la refleja.** Cualquier endpoint backend protegido por `RequireModule` revalida contra el set fresco del usuario. La UI es solo un espejo conveniente.
2. **Fail-closed siempre.** Si el bootstrap no cargó (error de red, sesión vencida, primer render), `puede(M.X)` retorna `false`. Nunca al revés.
3. **Constantes espejadas, no strings literales.** En backend `ModuleCode.CONTABILIDAD`, en frontend `M.CONTABILIDAD`. Strings literales en código de aplicación son bug en code review.
4. **`is_admin` es solo bypass — no autoriza nada por sí mismo en la BD.** Si un admin pierde el flag, el siguiente refresh lo deja sujeto a sus permisos normales.
5. **Las claves de módulo del ERP son inmutables.** Coinciden 1:1 con los strings en `Formulario.modulo` (mayúsculas, con tilde donde corresponde — `NÓMINA`). Renombrarlas rompe el sistema.
6. **El plan contratado lo dicta el ERP, no SAVI.** SAVI lee `SEO.Modulo` pero no lo modifica. Si el cliente contrata un módulo nuevo, el ERP lo refleja en `SEO.Modulo` y SAVI lo verá en el próximo bootstrap o polling.

## 9. Qué está explícitamente fuera de alcance

- **Granularidad por acción**. El ERP la tiene (`PermisoAccionUsuario`) pero SAVI por ahora solo gating a nivel módulo. Si en el futuro un usuario tiene que ver una vista pero sin botón de eliminar, escalamos el modelo.
- **Sincronización activa con el portal SEO**. Asumimos que el ERP mantiene `SEO.Modulo` actualizada. SAVI solo lee.
- **Cache server-side del bootstrap**. Por ahora cada llamada a `/auth/me/bootstrap` consulta `SEO.Modulo` y `PermisoFormulario`. Si el costo sube, cacheamos en Redis con TTL corto.
- **Auditoría de accesos denegados**. Hoy se loguea structuredly el 403, pero no se persiste en una tabla de auditoría. Si el equipo de seguridad lo pide, se agrega.

## 10. Aplicación a las consultas del chat

**Esto es trabajo futuro y se aborda en un documento aparte.** El sistema descrito aquí cubre la autorización a nivel de **endpoints HTTP y vistas UI**. Las tools del agente IA (`consultar_libre`, `consultar_datos`) acceden a datos del ERP y deben respetar las mismas reglas de módulo, pero requieren un mecanismo adicional: mapear esquemas/tablas de Postgres y entidades semánticas a códigos de módulo, y filtrar el catálogo expuesto al LLM. Se detallará una vez confirmado el plan general.
