# Multi-BD del ERP — Estado de la implementación

> Última actualización: 2026-09-13.
> Documentos hermanos:
> [`multi_erp_databases_spec.md`](multi_erp_databases_spec.md) (diseño y
> decisiones) · [`multi_erp_databases_frontend_guide.md`](multi_erp_databases_frontend_guide.md)
> (cómo seguir el frontend).

---

## Resumen en una línea

**Backend y frontend completos y verificados end-to-end (Fases 1-8).**

Validación corrida el 2026-09-13 sobre `backend/`:
`ruff check app` limpio · `pyright app` 0 errores · **173 tests pasando**, 1 skip.
Frontend: `biome lint` limpio · `vue-tsc --build` 0 errores · 34 tests (Vitest),
1 falla preexistente sin relación (`App.spec.ts`, falta Pinia en el montaje
del test — no lo introdujo este trabajo).

Los 10 tests agregados el mismo día cierran los huecos que dejaba el
checklist de la §12 de la spec sin cubrir (ver esa sección abajo):
rechazo real de un Postgres sin el esquema del ERP, `409` antes de abrir
el SSE, inmutabilidad de la base de una conversación, y las migraciones
corriendo de verdad sobre SQLite en sus dos caminos (BD nueva y BD
existente con backfill).

---

## Fases

| Fase | Descripción | Estado |
|---|---|---|
| 1 | Tabla `erp_databases` + cifrado Fernet + `ErpEngineRegistry` | ✅ hecho y verificado |
| 2 | Identidad calificada `(erp_database_id, user_id)` + login `USUARIO@CODE` | ✅ hecho y verificado |
| 3 | API de administración: CRUD + test de conexión + guards de la default | ✅ hecho y verificado |
| 4 | Permisos por base (D3, sin herencia) + `GET /erp-databases/available` | ✅ hecho y verificado |
| 5 | Turno del chat multi-base + `409 erp_database_unavailable` | ✅ hecho y verificado |
| 6 | Frontend: sección administración (`/admin`) + mover consumo global | ✅ hecho y verificado |
| 7 | Frontend: selector de base en chat + chip + estado degradado + login `@CODE` | ✅ hecho y verificado |
| 8 | Instalador: clave Fernet, `SAVI_ADMIN_LOGINS`, `env.template`, docs | ✅ hecho |

---

## Bug encontrado y corregido al verificar la Fase 7 end-to-end (2026-09-13)

**Síntoma:** un usuario que abre una conversación contra un cliente
distinto al de su login (el caso central de D10 — "atender varios
clientes sin cerrar sesión") recibía `404` al abrirla, no la veía en el
listado y no podía mandar turnos.

**Causa:** `conversations.erp_database_id` cumplía dos roles que
chocan: la base **consultada** (fijada al crear, D2) y la base de
**identidad** del dueño (usada por `list_for_user`, el ownership check
de `chat`/`get`/`rename`/`delete`, y "mi consumo"). Mientras una
instalación atendía un solo cliente los dos roles coincidían y el bug
quedaba oculto — nunca se había probado una conversación contra una
base distinta a la de login.

**Corrección:** columna nueva `owner_erp_database_id` (migración
`d1a4c8f0e921`, con backfill en la propia migración — es una copia de
una columna existente, no depende de `.env`). `erp_database_id` sigue
siendo la base consultada; `owner_erp_database_id` es la identidad. Los
filtros de dueño (`ConversationOwner.owns`, `list_for_user`, "mi
consumo") pasan a comparar contra la columna nueva. El ranking global
de consumo por cliente (`usage.per_user`, admin) sigue agrupando por la
base consultada a propósito — es correcto para facturar por cliente.

Test de regresión: `test_conversation_visible_and_ownable_across_queried_databases`
en `tests/unit/modules/erp_databases/test_identity_isolation.py`.

---

## Huecos del checklist de testing (§12 de la spec) cerrados el 2026-09-13

Auditando la spec contra el código se encontró que cuatro puntos del
"mínimo exigible" de §12 funcionaban (verificados a mano o por E2E) pero
no tenían test automatizado. Se cerraron los cuatro:

| Punto de §12 | Test nuevo |
|---|---|
| Test de conexión rechaza un Postgres sin el esquema del ERP | `tests/unit/modules/erp_databases/test_postgres_connection_tester.py` — contra un Postgres real (se salta si no hay uno alcanzable), crea y borra su propia base de prueba |
| Base inactiva: `POST /chat` da `409` antes de abrir el SSE | `tests/unit/modules/chat/test_database_unavailable_before_stream.py` — llama al handler HTTP directo con dobles mínimos |
| Inmutabilidad de la base de una conversación (D2, R1) | `tests/unit/modules/conversations/test_database_immutability.py` (módulo nuevo — `conversations` no tenía tests) |
| Migración aplica sobre SQLite nueva y existente | `tests/unit/infrastructure/test_ensure_schema_migration_paths.py` — corre `ensure_schema()` de verdad en los dos caminos, no `create_all` directo |

Con estos, la suite pasó de 163 a **173 tests**.

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
- **Frontend (Fases 6-7), con Playwright contra los dos dev servers reales**:
  CRUD de administración completo (crear, probar conexión con contraseña
  mala y buena, editar sin pisar la contraseña, desactivar/activar,
  predeterminar, eliminar); `/admin` con guard para no-admin;
  `/consumo` redirige según rol; login `ADMIN@NORTE` con la misma
  respuesta que una contraseña mala para un código inexistente; selector
  de cliente en una conversación nueva; una conversación abierta contra
  un cliente **distinto** al de login (D10) responde con datos reales de
  esa base; chip de solo lectura con el nombre del cliente; banner y
  Composer deshabilitado cuando la base de la conversación se desactiva.
  Encontró y motivó la corrección de identidad documentada arriba.

---

## Migraciones Alembic

Tres revisiones nuevas, encadenadas sobre `4a8dcb6945b3`:

1. `b1f4c27ae903_add_erp_databases_table` — tabla `erp_databases` con los
   tres índices únicos parciales (`code`, `name`, `is_default`).
2. `c93e5a1d7f42_qualify_identity_with_erp_database` — columnas
   `erp_database_id` en `conversations`, `refresh_token` y `audit_query`,
   índices por usuario recompuestos a `(erp_database_id, user_id)`.
3. `d1a4c8f0e921_split_conversation_owner_from_queried_database` —
   columna `owner_erp_database_id` en `conversations` (identidad del
   dueño, separada de la base consultada), con backfill propio y el
   índice `(owner_erp_database_id, user_id)`.

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
- `conversations`: columna `erp_database_id` (inmutable, la CONSULTADA) +
  `owner_erp_database_id` (la de IDENTIDAD del dueño — ver el bug de
  arriba), value object `ConversationOwner`, scoping de listado y
  ownership por `(owner_erp_database_id, usuario)`.
- `chat`: `erp_database_id` a través del turno → runner → tools MCP
  (siguen siendo **4** tools, sin cambio); `409` antes del SSE. El
  ownership del chat compara `owner_erp_database_id`.
- `usage`: "mi consumo" scopeado por `(owner_erp_database_id, user_id)`;
  el ranking global por cliente (`per_user`, admin) sigue agrupando por
  `erp_database_id` (la consultada) a propósito.
- `infrastructure/database/pool.py`: se eliminó el engine global del ERP.
- `launcher.py`: el diagnóstico arma un engine descartable desde el `.env`.

Tests nuevos en `tests/unit/modules/erp_databases/`:
`test_credential_cipher`, `test_engine_registry`, `test_repository_and_seed`,
`test_identity_isolation`, `test_manage_use_case`,
`test_permissions_per_database`; más `test_qualified_login` y
`test_savi_admin_gate` en `tests/unit/modules/auth/`.

---

## Cómo continuar

El requerimiento está completo (Fases 1-8). Pendientes reales:

1. Commitear el trabajo — está esperando confirmación explícita del
   usuario (regla del proyecto, `CLAUDE.md` §12-13).
2. Las dos preguntas abiertas de §13 de la spec (pools, limpieza de
   `ERP_DB_PASSWORD`) — no bloquean nada.
3. Si se agrega un tercer/cuarto cliente real, repetir al menos el caso
   D10 (conversación contra un cliente distinto al de login) — es el
   que reveló el bug de identidad.

---

## Decisiones abiertas (no bloquean)

- **§13.4 de la spec** — tamaño de los pools del registry (hoy: tope 10
  engines, `pool_size=3`). Ajustable con `ERP_MAX_OPEN_ENGINES`.
- **§13.6 de la spec** — limpieza de `ERP_DB_PASSWORD` del `.env` tras el
  seed. Propuesta: paso manual documentado + aviso en el panel de admin.
