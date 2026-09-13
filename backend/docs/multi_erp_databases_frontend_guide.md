# Multi-BD del ERP — Guía de implementación del frontend

> Estado: **backend completo y verificado; frontend pendiente.**
> Complementa a [`multi_erp_databases_spec.md`](multi_erp_databases_spec.md).
> Esta guía es el mapa para retomar el frontend (Fases 6 y 7) sin volver
> a reconstruir el contexto.

---

## 1. Qué ya expone el backend (contrato listo)

Todo esto está implementado, probado y andando contra `farmacias_similares`.
El frontend solo tiene que consumirlo.

### Administración (solo admin de SAVI) — prefijo `/admin/erp-databases`

| Método | Ruta | Body / query | Devuelve |
|---|---|---|---|
| `GET` | `/admin/erp-databases` | `?include_inactive=bool` | `ErpDatabaseResponse[]` |
| `POST` | `/admin/erp-databases` | `SaveErpDatabaseRequest` | `ErpDatabaseResponse` (201) |
| `GET` | `/admin/erp-databases/{id}` | — | `ErpDatabaseResponse` |
| `PATCH` | `/admin/erp-databases/{id}` | `SaveErpDatabaseRequest` | `ErpDatabaseResponse` |
| `POST` | `/admin/erp-databases/test-connection` | `SaveErpDatabaseRequest` + `?database_id=uuid` opcional | `ConnectionTestResponse` |
| `POST` | `/admin/erp-databases/{id}/set-default` | — | `ErpDatabaseResponse` |
| `POST` | `/admin/erp-databases/{id}/activate` | — | `ErpDatabaseResponse` |
| `POST` | `/admin/erp-databases/{id}/deactivate` | — | `ErpDatabaseResponse` (422 si es default) |
| `DELETE` | `/admin/erp-databases/{id}` | — | `204` (422 si es default) |

**`ErpDatabaseResponse`** (nunca trae la contraseña):
```ts
{
  id: string; code: string; name: string; host: string; port: number;
  database: string; username: string; statement_timeout_ms: number;
  is_default: boolean; is_active: boolean;
  credentials_unreadable: boolean;   // clave Fernet cambió → re-cargar pass
  is_usable: boolean;                // false si inactiva/eliminada/ilegible
  last_connection_ok_at: string | null;
  created_at: string; updated_at: string;
}
```

**`SaveErpDatabaseRequest`**:
```ts
{
  code: string;        // ^[A-Za-z0-9_-]{2,32}$  (sin @ — es el separador del login)
  name: string;
  host: string; port?: number; database: string; username: string;
  password?: string;   // VACÍO al editar = conservar la guardada
  statement_timeout_ms?: number;
}
```

**`ConnectionTestResponse`**:
```ts
{ ok: boolean; detail: string; razon_social: string | null; missing_tables: string[] }
```

### Selector del chat (cualquier usuario autenticado)

| Método | Ruta | Devuelve |
|---|---|---|
| `GET` | `/erp-databases/available` | `{ id, code, name }[]` |

Solo lista las bases **donde el usuario tiene acceso** (D3): activas y donde
su `codigo` existe y está activo. No expone host/puerto/credenciales.

### Cambios en endpoints existentes

- `POST /conversations` acepta `erp_database_id?: string` en el body.
  Ausente = base de identidad del usuario. Valida acceso D3: `409` si el
  usuario no tiene acceso a esa base.
- `GET /conversations` y `POST /conversations` devuelven `erp_database_id`
  en cada conversación (para el chip de la sidebar).
- `POST /chat`: valida que la base de la conversación siga disponible
  **antes** de abrir el SSE. Si no: `409` con
  `errorCode: "erp_database_unavailable"` (más `detail` y `erp_database_id`).
- Login (`POST /auth/login`): el campo `login` acepta `USUARIO@CODE`. El
  contrato del body **no cambia** — el `@CODE` viaja dentro de `login`.

---

## 2. Patrones del frontend a respetar (no reinventar)

Verificado leyendo el código actual:

- **El store ES la capa de datos.** No hay vue-query. Cada store tiene
  sus `ref` de datos + `loading` + `error`, y llama al service. Ver
  `modules/usage/stores/usageStore.ts` como molde exacto.
- **Service = wrapper de `HttpClient`.** `new HttpClient('/prefijo')` y
  métodos `get/post/patch/delete`. Ver `modules/usage/services/usageService.ts`.
- **Contrato público por módulo en `index.ts`.** Otros módulos importan
  SOLO desde `@/modules/<x>`, nunca de subcarpetas. Ver
  `modules/permisos/index.ts`.
- **`HttpClient` ya centraliza el manejo de `errorCode`** en `request()`
  (`lib/HttpClient.ts:145`). Hoy trata `module_access_denied`; ahí mismo
  se engancha `erp_database_unavailable`.
- **Guard del router** en `router/index.ts` maneja `requiresAuth`,
  `hideForAuthed` y `requireModule`. **No** maneja `requiresAdmin` — hay
  que agregarlo (chequeo `authStore.user.is_admin`).
- **`authStore.user`** ya tiene `{ id, login, full_name, is_admin }`
  (`modules/auth/types.ts`). El `is_admin` alcanza para el guard del
  admin; el escape `SAVI_ADMIN_LOGINS` es server-side y no se refleja en
  el token, así que la UI se guía por `is_admin` y el backend es la
  autoridad final (un no-admin con escape verá 403 → 200 al entrar).
- **Claves de `localStorage`** centralizadas en `lib/storageKeys.ts`.
- **shadcn-vue + Tailwind 4 + `cn()`**. Componentes UI base en
  `components/ui/`. Leer skills `frontend-shadcn-guide` y `tailwind-4`
  antes de tocar componentes.

> **Regla de oro que aplica también acá:** nunca mostrar SQL crudo ni
> nombres internos de tools al usuario. Y para bases: **nunca** mostrar
> host/puerto/credenciales fuera de la sección de administración.

---

## 3. Orden recomendado

**Admin primero (Fase 6), chat después (Fase 7).** Razón concreta: sin la
sección de administración, la única forma de registrar un segundo cliente
es por API a mano. Con el CRUD andando, se pueden cargar clientes reales y
recién ahí el chat multi-base se prueba con más de una base. El chat
depende de que haya bases; el admin no depende del chat.

---

## 4. Fase 6 — Sección administración

### 4.1 Módulo nuevo `frontend/src/modules/admin/`

```
modules/admin/
├── components/
│   ├── ErpDatabaseTable.vue      # listado + acciones (activar/desactivar/default/eliminar)
│   ├── ErpDatabaseForm.vue       # alta/edición; password vacío = conservar
│   ├── TestConnectionButton.vue  # botón independiente; muestra razon_social
│   └── ConfirmDeactivateDialog.vue
├── services/erpDatabaseService.ts   # HttpClient('/admin/erp-databases')
├── stores/erpDatabaseStore.ts       # lista + loading/error, patrón usageStore
├── views/
│   ├── AdminLayout.vue           # layout con nav lateral propia (distinta del chat)
│   ├── ErpDatabasesView.vue      # CRUD de bases
│   └── AdminUsageView.vue        # consumo GLOBAL (mueve SystemUsage/KPIs/Tarifas)
├── types.ts
└── index.ts                      # contrato público
```

### 4.2 Rutas (anidadas, con guard de admin)

```
/admin                → redirect a /admin/bases-datos
/admin/bases-datos    → ErpDatabasesView   (meta.requiresAdmin)
/admin/consumo        → AdminUsageView      (meta.requiresAdmin)
/consumo              → redirect a /admin/consumo (no romper enlaces viejos)
```

Agregar a `router/index.ts`:
- `meta.requiresAdmin?: boolean` en la interfaz `RouteMeta`.
- En el guard: si `to.meta.requiresAdmin && !authStore.user?.is_admin`
  → redirigir a `/` (o a `/sin-acceso`).

### 4.3 Detalles que ya están decididos (no re-litigar)

- **"Mi consumo" NO se mueve a `/admin`.** `MyUsagePanel` es de cualquier
  usuario. Solo el consumo de sistema, KPIs y simulador de tarifas van a
  `/admin/consumo`. Propuesta: "mi consumo" → `/perfil` (ya existe y ya es
  personal). Mantener `/consumo` como redirect.
- **Formulario**: nombre, host, puerto, base, usuario, contraseña, timeout.
  Al **editar**, la contraseña arranca vacía y solo se manda si el usuario
  escribe una nueva (vacío = conservar).
- **"Probar conexión"** es un botón independiente y además corre implícito
  antes de guardar (el backend lo fuerza). Al éxito muestra `razon_social`
  y, si el campo nombre está vacío, la propone.
- **Estados en la tabla**: activa / desactivada / `credentials_unreadable`
  ("credenciales ilegibles — volvé a ingresar la contraseña"). La default
  no se puede eliminar ni desactivar (el backend devuelve 422; la UI
  debería deshabilitar esos botones y mostrar por qué).

---

## 5. Fase 7 — Chat y login

### 5.1 Servicio y store

- `chat` ya tiene `conversationService`. Agregar
  `availableDatabases()` → `GET /erp-databases/available`, o exponerlo
  desde el módulo `admin` vía su `index.ts` y consumirlo en chat. (Recomendado:
  un `erpDatabaseService.available()` en `admin` y que chat lo importe del
  contrato público de `admin`.)
- `chatStore`: agregar `availableDatabases` + la base seleccionada para la
  **conversación nueva** (no para las existentes).

### 5.2 Selector de base — solo al iniciar

- En `WelcomeScreen.vue` / `Composer.vue`: `<select>` visible **solo
  cuando no hay conversación activa** (`messages.length === 0`). Default
  preseleccionada. Al crear la conversación se manda `erp_database_id`.
- Una vez creada, la base es **inmutable** (D2): en una conversación
  existente se muestra como chip de solo lectura, no como control.

### 5.3 Chip del cliente por conversación

- En `Sidebar.vue` / `ConversationItem.vue`: mostrar el `name` del cliente
  por conversación. `GET /conversations` ya devuelve `erp_database_id`; hay
  que resolver id→nombre con la lista de `available` (o guardar un mapa
  id→name en el store). **Sin esto la lista es inusable** con varios
  clientes: los títulos autogenerados se parecen entre sí.

### 5.4 Estado degradado (base inactiva/eliminada)

- El backend ya devuelve `409 { errorCode: "erp_database_unavailable" }`
  al enviar un turno contra una base no disponible.
- Enganchar en `HttpClient.request()` (junto a `module_access_denied`) o
  en el consumer del SSE (`agentService`/`chatStore`): mostrar banner y
  **deshabilitar el Composer** con el motivo. El historial se sigue
  leyendo (mismo patrón de solo-lectura que ya usa `/share/:id`).
- `usePermisosPolling` ya detecta cambios de permisos en caliente; conviene
  extenderlo (o sumar un chequeo liviano) para detectar que la base de la
  conversación abierta se desactivó, en vez de descubrirlo al enviar.

### 5.5 Login con `@CODE`

- `LoginView.vue`: el campo usuario acepta `JPEREZ` o `JPEREZ@NORTE`. El
  body no cambia (`{ login, password }`), el `@CODE` viaja en `login`.
- Autocompletado: guardar en `localStorage` (vía `lib/storageKeys.ts`) los
  `code` que ese equipo ya usó con éxito y ofrecerlos con `<datalist>`.
  Guardar el `code` **solo tras login exitoso**. Nunca usuario ni password.
- **El mensaje de error NO cambia y no debe cambiar**: cliente inexistente,
  usuario inexistente y contraseña mala comparten la misma respuesta
  (el backend lo garantiza; si la UI inventara "cliente no encontrado"
  rompería la mitigación anti-enumeración).

---

## 6. Testing frontend

Vitest ya está configurado (ver `vitest.config.ts` y `src/lib/__tests__/`).
Mínimo sugerido:

- El selector de base solo aparece sin conversación activa.
- `erp_database_unavailable` deshabilita el Composer y muestra el banner.
- El login parte `JPEREZ@NORTE` correctamente antes de mandar (o lo manda
  tal cual — el split real es server-side; el front solo lo transmite).
- El guard de admin redirige a un no-admin fuera de `/admin`.

---

## 7. Riesgos específicos del frontend

| # | Riesgo | Mitigación |
|---|---|---|
| F1 | Mostrar host/credenciales a un usuario no admin | El selector usa `available` (solo id/code/name); el CRUD está tras el guard de admin |
| F2 | Permitir cambiar la base de una conversación existente | El selector solo aparece sin conversación activa; chip de solo lectura después |
| F3 | Inventar un mensaje de error de login que distinga cliente inexistente | Usar el mensaje genérico del backend tal cual (§5.5) |
| F4 | Lista de conversaciones ambigua con varios clientes | Chip del cliente por conversación (§5.3), no opcional |
| F5 | Guard de admin como única defensa | Es solo UX; el backend valida en cada endpoint (autoridad real) |
