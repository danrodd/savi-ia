# Multi-BD del ERP — Estado de la implementación

> Última actualización: 2026-09-13.
> Documentos hermanos:
> [`multi_erp_databases_spec.md`](multi_erp_databases_spec.md) (diseño y
> decisiones) · [`multi_erp_databases_frontend_guide.md`](multi_erp_databases_frontend_guide.md)
> (cómo seguir el frontend).

---

## Resumen en una línea

**Backend completo y verificado. Falta todo el frontend (Fases 6 y 7).**

Validación corrida el 2026-09-13 sobre `backend/`:
`ruff check app` limpio · `pyright app` 0 errores · **162 tests pasando**, 1 skip.

---

## Fases

| Fase | Descripción | Estado |
|---|---|---|
| 1 | Tabla `erp_databases` + cifrado Fernet + `ErpEngineRegistry` | ✅ hecho y verificado |
| 2 | Identidad calificada `(erp_database_id, user_id)` + login `USUARIO@CODE` | ✅ hecho y verificado |
| 3 | API de administración: CRUD + test de conexión + guards de la default | ✅ hecho y verificado |
| 4 | Permisos por base (D3, sin herencia) + `GET /erp-databases/available` | ✅ hecho y verificado |
| 5 | Turno del chat multi-base + `409 erp_database_unavailable` | ✅ hecho y verificado |
| 6 | Frontend: sección administración (`/admin`) + mover consumo global | ⬜ pendiente |
| 7 | Frontend: selector de base en chat + chip + estado degradado + login `@CODE` | ⬜ pendiente |
| 8 | Instalador: clave Fernet, `SAVI_ADMIN_LOGINS`, `env.template`, docs | ✅ hecho |

> El orden real de ejecución fue 1 → 2 → 3 → 4 → 5 → 8. La Fase 2 va antes
> de que exista una segunda base porque corrige el defecto latente de
> identidad (§3.2 de la spec): agregar un segundo cliente sin eso cruzaría
> datos entre clientes.

**Regla operativa:** recién al terminar la Fase 4 es seguro registrar un
segundo cliente. Antes de eso el aislamiento no estaba completo. Hoy ya
está, así que se puede cargar clientes reales por API mientras se construye
el frontend.

---

## Qué se verificó end-to-end contra el ERP real (`farmacias_similares`)

- **Seed de arranque**: la BD del `.env` se siembra como default y la
  contraseña queda **cifrada** en `savi.db` (`gAAAAABqo...`, no `1234`).
- **Consulta al ERP por el registry** (no por el engine global viejo):
  `Empresa.Empresa` → "FARMACIAS DE SIMILARES COLOMBIA SAS", 60 usuarios.
- **Read-only forzado** sigue vigente en cada engine del registry.
- **Login calificado**: `JPEREZ@NORTE` resuelve solo esa base; cliente
  inexistente, usuario inexistente y contraseña mala dan el mismo error
  y **el mismo tiempo** (242/254/250 ms — el oráculo de tiempo quedó cerrado).
- **CRUD de administración** (con admin real del ERP): test de conexión
  contra la base real, `422` si la base no existe (no persiste), sin fuga
  de contraseña en las respuestas, `422` al eliminar/desactivar la default,
  `422` con mensaje claro ante `code` duplicado.
- **D3**: admin del ERP → 16 módulos; un no-admin → 1 módulo (filtrado por
  sus permisos); usuario inexistente en esa base → sin acceso.
- **Turno con base no disponible** → `409 erp_database_unavailable` **antes**
  de abrir el SSE.

---

## Migraciones Alembic

Dos revisiones nuevas, encadenadas sobre `4a8dcb6945b3`:

1. `b1f4c27ae903_add_erp_databases_table` — tabla `erp_databases` con los
   tres índices únicos parciales (`code`, `name`, `is_default`).
2. `c93e5a1d7f42_qualify_identity_with_erp_database` — columnas
   `erp_database_id` en `conversations`, `refresh_token` y `audit_query`,
   índices por usuario recompuestos a `(erp_database_id, user_id)`.

Verificadas en los **dos** caminos de SQLite (BD nueva vía `create_all` +
`stamp`, y BD existente vía `upgrade`) y con `downgrade` real (batch mode).
El backfill de filas legadas (`erp_databases/infrastructure/backfill.py`)
corre al arrancar, después del seed.

> **Pendiente operativo (no bloquea):** tras el primer arranque exitoso
> conviene vaciar `ERP_DB_PASSWORD` del `.env` (queda duplicada: cifrada en
> la BD y en claro en el archivo). Documentado en `DISTRIBUCION.md`.

---

## Mapa del código nuevo (backend)

Módulo nuevo `app/modules/erp_databases/` (triada Clean completa):

```
erp_databases/
├── domain/
│   ├── entities/erp_database.py          # entidad + is_usable + url (con quote)
│   ├── value_objects/database_code.py    # normalize_code, ^[A-Z0-9_-]{2,32}$
│   ├── interfaces/                        # repository, credential_cipher, connection_tester
│   └── exceptions/                        # NotFound / Unavailable(409) / Duplicate(422)
├── application/
│   ├── dtos/            # SaveErpDatabaseDTO, ErpDatabaseDTO (sin password), AvailableDatabaseDTO
│   ├── requests/ responses/
│   └── use_cases/       # ManageErpDatabasesUseCase, ListAvailableDatabasesUseCase
└── infrastructure/
    ├── persistence/     # ErpDatabaseModel + repo (frontera del cifrado)
    ├── security/fernet_credential_cipher.py
    ├── postgres_connection_tester.py     # SELECT 1 + verificación de esquema ERP
    ├── engine_registry.py                # pool por cliente, LRU, invalidación
    ├── connection_provider.py            # id → engine, valida is_usable
    ├── seed.py  backfill.py
    └── http/            # routes (admin) + public_routes (available)
```

Cambios en módulos existentes:
- `auth`: identidad calificada en `AuthenticatedUser`, `TokenClaims`,
  `JwtTokenService` (subject `db_id:user_id`, rechaza tokens viejos),
  `LoginUseCase` (`@CODE` + piso de tiempo), `RefreshTokensUseCase`
  (valida base activa), `UserRepositoryFactory` + factories de
  permisos/plan por base, `ResolveModulesForDatabaseUseCase` (D3), gate
  `SaviAdminDep`.
- `conversations`: columna `erp_database_id` (inmutable), value object
  `ConversationOwner`, scoping de listado y ownership por `(base, usuario)`.
- `chat`: `erp_database_id` a través del turno → runner → tools MCP
  (siguen siendo **4** tools, sin cambio); `409` antes del SSE.
- `usage`: agregados scopeados por `(erp_database_id, user_id)`.
- `infrastructure/database/pool.py`: se eliminó el engine global del ERP.
- `launcher.py`: el diagnóstico arma un engine descartable desde el `.env`.

Tests nuevos en `tests/unit/modules/erp_databases/`:
`test_credential_cipher`, `test_engine_registry`, `test_repository_and_seed`,
`test_identity_isolation`, `test_manage_use_case`,
`test_permissions_per_database`; más `test_qualified_login` y
`test_savi_admin_gate` en `tests/unit/modules/auth/`.

---

## Cómo continuar

1. Leer [`multi_erp_databases_frontend_guide.md`](multi_erp_databases_frontend_guide.md):
   tiene el contrato del backend ya listo, los patrones del frontend a
   respetar, y el plan de Fases 6 y 7 con el detalle de cada archivo.
2. Orden recomendado: **admin primero, chat después** (el chat necesita
   bases cargadas para probarse con más de una).
3. Antes de tocar componentes Vue, leer las skills del frontend
   (`enterprise-frontend-architecture`, `vue-best-practices`,
   `frontend-shadcn-guide`, `tailwind-4`) — ver tabla de auto-invoke en
   `CLAUDE.md` §6.

---

## Decisiones abiertas (no bloquean)

- **§13.4 de la spec** — tamaño de los pools del registry (hoy: tope 10
  engines, `pool_size=3`). Ajustable con `ERP_MAX_OPEN_ENGINES`.
- **§13.6 de la spec** — limpieza de `ERP_DB_PASSWORD` del `.env` tras el
  seed. Propuesta: paso manual documentado + aviso en el panel de admin.
