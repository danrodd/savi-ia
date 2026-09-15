# Fase 3 — API de administración de clientes

> Parte de: [PRD — Clientes con varias bases](00-prd.md)
> Estado: **propuesta**. Depende de la [Fase 2](02-fase-acceso-y-login.md).
> Cambio visible: clientes, sucursales e identidad administrables por API.

## Resultado esperado

- [ ] CRUD de clientes en `/admin/erp-clients`.
- [ ] Bases con `client_id` obligatorio; mover base y designar identidad.
- [ ] Invariantes de PRD §2.3 aplicadas en los casos de uso.
- [ ] Confirmación explícita con conteo de conversaciones afectadas (C10).
- [ ] Export/import v2 agrupado por cliente, con lectura de v1.
- [ ] Filtro `client_id` en `/usage/system`, `/usage/kpis` y `/usage/conversations`.
- [ ] Tests de reglas y de ningún response con contraseñas.

---

## 1. Endpoints de clientes

Router nuevo `erp_databases/infrastructure/http/client_routes.py`,
prefijo `/admin/erp-clients`, todos con `SaviAdminDep` (ya con la regla
C9 de la Fase 2). `"admin"` ya está en `_API_PREFIXES` de `main.py`, así
que no hay que tocarlo.

| Método | Ruta | Body / query | Respuesta | Reglas |
|---|---|---|---|---|
| `GET` | `""` | `?include_inactive=bool` | `list[ErpClientResponse]` | Eliminados nunca. |
| `POST` | `""` | `{code, name}` | `201 ErpClientResponse` | Código y nombre únicos. El primer cliente creado queda predeterminado. |
| `GET` | `/{id}` | — | `ErpClientResponse` | `404` si no existe. |
| `PATCH` | `/{id}` | `{code, name}` | `ErpClientResponse` | Ver §1.2 sobre el cambio de código. |
| `POST` | `/{id}/activate` | — | `ErpClientResponse` | |
| `POST` | `/{id}/deactivate` | — | `ErpClientResponse` | `422` si es el predeterminado. Invalida los engines de todas sus bases. |
| `POST` | `/{id}/set-default` | — | `ErpClientResponse` | `422` si está inactivo o no tiene base de identidad utilizable. |
| `DELETE` | `/{id}` | — | `204` | Baja lógica idempotente. `422` si es el predeterminado. Da de baja lógica sus bases e invalida engines. |

### 1.1 `ErpClientResponse`

```json
{
  "id": "…",
  "code": "FARMX",
  "name": "Farmacias X",
  "is_default": false,
  "is_active": true,
  "is_usable": true,
  "database_count": 3,
  "identity_database_id": "…",
  "identity_database_name": "Sede Centro",
  "created_at": "…",
  "updated_at": "…"
}
```

`identity_database_id` es `null` cuando el cliente todavía no tiene
bases. Ese cliente existe pero **no permite login** (§2.1 de la Fase 2).
La UI lo muestra como "incompleto".

### 1.2 Cambiar el código de un cliente

Se permite, porque corregir un código mal elegido es una necesidad real.
Pero cambia el login de todos sus usuarios. La respuesta no lo impide:
**la advertencia es responsabilidad de la UI** (Fase 4). El API lo
documenta en el docstring del endpoint.

## 2. Cambios en `/admin/erp-databases`

| Endpoint | Cambio |
|---|---|
| `GET ""` | Nuevo query `?client_id=`. Sin él, lista todas, como hoy. |
| `POST ""` | `SaveErpDatabaseRequest` suma `client_id` **obligatorio**. Si el cliente no tiene bases, la nueva queda como identidad. **Se elimina** la creación implícita de cliente que dejó la Fase 1. |
| `PATCH /{id}` | `client_id` se ignora: mover es una operación aparte (§3.2), para no disparar un cambio de identidad desde un formulario de edición. |
| `POST /{id}/set-default` | **Se elimina.** El predeterminado es del cliente. |
| `POST /{id}/deactivate`, `DELETE /{id}` | `422` si es la identidad de un cliente con otras bases activas ("designá otra base de identidad primero"). Si es la única base, `422` con "desactivá el cliente". |
| **+** `POST /{id}/set-identity` | Ver §3.1. |
| **+** `POST /{id}/move` | Ver §3.2. |

`ErpDatabaseResponse` pierde el `is_default` calculado que dejó la Fase 1.
Suma `client_id`, `client_code`, `client_name` e `is_identity`. El
frontend se actualiza en la misma entrega (Fase 4), así que el cambio de
contrato no queda expuesto entre versiones.

## 3. Operaciones sensibles (C10)

### 3.1 `POST /admin/erp-databases/{id}/set-identity`

Body: `{ "confirm_owner_change": false }`

1. La base tiene que estar activa y utilizable; si no, `422`.
2. Contar las conversaciones no eliminadas con
   `owner_erp_database_id = <identidad actual del cliente>`.
3. Si el conteo es mayor que 0 y `confirm_owner_change` es `false`, `409`:

```json
{
  "errorCode": "identity_change_requires_confirmation",
  "message": "Los usuarios de este cliente dejarán de ver 42 conversaciones anteriores.",
  "affected_conversations": 42
}
```

4. Con confirmación, o sin conversaciones afectadas: quitar
   `is_identity` a la anterior y marcar la nueva, en **una sola
   transacción**, bajando primero la anterior por el índice único
   parcial, igual que hace hoy `set_default`.
5. Invalidar la caché de cliente de la Fase 2 (§2.2).

**Por qué `409` y no una simple advertencia en la UI:** la regla la
tiene que hacer cumplir el backend. Un script, un import o un frontend
viejo no pueden cambiar la identidad sin haber visto el número. Las
conversaciones no se borran: siguen en la BD con su owner original y
vuelven a ser visibles si la identidad vuelve a esa base.

### 3.2 `POST /admin/erp-databases/{id}/move`

Body: `{ "client_id": "…", "confirm_owner_change": false }`

| Caso | Comportamiento |
|---|---|
| La base **no** es identidad | Se mueve. Si el cliente destino no tenía bases, queda como identidad. Sin conversaciones afectadas (el owner no depende de ella). |
| Es identidad y el cliente origen **tiene otras bases** | `422`: "designá otra base de identidad antes de moverla". |
| Es identidad y es **la única** base del origen | Mismo `409` de §3.1 si hay conversaciones con owner en ella. Con confirmación, se mueve y el cliente origen queda sin bases, en estado incompleto. El body del `409` agrega `old_login_code` y `new_login_code`, para que la UI advierta el cambio de login (R2). |
| Código de base repetido en el destino | `422`: "ya existe una base con código X en ese cliente". |
| Destino inactivo o eliminado | `422`. |

**No se borra automáticamente el cliente origen vacío.** Se deja
incompleto para que el administrador decida. Borrarlo solo haría que un
login `@ORIGEN` pase de "credenciales inválidas" a... "credenciales
inválidas": el mismo resultado, pero sin forma de revertirlo desde la UI.

## 4. Export/import v2

### 4.1 Formato

```json
{
  "version": 2,
  "clients": [
    {
      "code": "FARMX",
      "name": "Farmacias X",
      "is_default": true,
      "databases": [
        { "code": "CENTRO", "name": "Sede Centro", "host": "…", "port": 5432,
          "database": "…", "username": "…", "password": "…",
          "statement_timeout_ms": 60000, "is_identity": true }
      ]
    }
  ]
}
```

El sobre cifrado con la contraseña de exportación no cambia
(`export_cipher.py`). Solo cambia el JSON interior.

### 4.2 Export

Clientes activos con sus bases activas y legibles. Un cliente cuyas bases
quedaron todas excluidas se exporta igual, con `databases: []`, para que
el destino replique la estructura.

### 4.3 Import

Best-effort por fila, igual que hoy:

1. **v1:** cada fila se trata como un cliente con una sola base
   (`code` = código de cliente y de base, `is_identity = true`). Es la
   misma regla que la migración de la Fase 1, así que un archivo viejo
   produce el mismo resultado que en una instalación migrada.
2. **v2:** por cada cliente, se crea o actualiza por `code` (nombre). Por
   cada base, se crea o actualiza por `(client, code)`, usando
   `ManageErpDatabasesUseCase` para conservar el test de conexión (D5) y
   el recifrado local (D4).
3. **Identidad:** si la fila `is_identity` difiere de la identidad actual
   del cliente local, **no** se cambia automáticamente. La fila se
   reporta como `updated` con `detail` "la base de identidad difiere;
   cambiala desde la administración". Aplicarla desde un archivo
   saltearía C10.
4. **Predeterminado:** se aplica solo si el cliente queda utilizable, como
   hoy.

`ImportRowResultDTO` suma `client_code`. `status` mantiene
`created | updated | failed`.

## 5. Consumo por cliente

`_resolve_filters` (`usage/infrastructure/http/routes.py`) suma
`client_id: UUID | None`. Los tres endpoints de administración lo
aceptan como query.

**Qué significa "consumo de un cliente":** el de las conversaciones cuya
base **consultada** (`conversations.erp_database_id`) pertenece al
cliente. No se usa la base de identidad del usuario, porque en modo
`cross_client` un agente de soporte de A que consulta a B consume por
cuenta de B. Es el criterio que va a necesitar la facturación del paso 4.

El repositorio agrega un `JOIN erp_databases ON conversations.erp_database_id`
filtrado por `client_id`. Revisar que el `->>` sobre JSON de `usage`
siga funcionando en SQLite con el `JOIN` (comentario de `types.py:26`).

## 6. Casos de uso

| Caso de uso | Archivo |
|---|---|
| `ManageErpClientsUseCase` | `application/use_cases/manage_erp_clients.py` |
| `ManageErpDatabasesUseCase` (se extiende: `set_identity`, `move`) | `application/use_cases/manage_erp_databases.py` |
| `ExportImportErpDatabasesUseCase` (v2) | `application/use_cases/export_import_erp_databases.py` |

Puerto nuevo para el conteo de C10, para que `erp_databases` no importe el
ORM de `conversations`:

```python
class ConversationOwnershipCounter(ABC):
    async def count_owned_by_database(self, database_id: UUID) -> int: ...
```

Su implementación vive en `conversations/infrastructure` y se inyecta en
`dependencies.py`.

Errores de dominio nuevos, mapeados en `shared/exceptions/handlers.py`:

| Excepción | Status | `errorCode` |
|---|---|---|
| `ErpClientNotFoundError` | `404` | `erp_client_not_found` |
| `DuplicateErpClientError` | `422` | (validación, igual que `DuplicateErpDatabaseError`) |
| `IdentityChangeRequiresConfirmationError` | `409` | `identity_change_requires_confirmation` |

## 7. Tests

| Test | Verifica |
|---|---|
| Crear cliente | El primero queda predeterminado; código y nombre duplicados dan `422`. |
| Primera base | Queda identidad; la segunda no. |
| Desactivar o eliminar predeterminado | `422`. |
| Eliminar cliente | Da de baja lógica sus bases e invalida engines (fake registry). |
| Identidad con otras bases | Desactivar, eliminar o mover dan `422`. |
| `set-identity` con conversaciones | `409` con el conteo exacto; sin confirmación no cambia nada; con confirmación cambia atómicamente. |
| `set-identity` sin conversaciones | Cambia sin pedir confirmación. |
| `move` | Base no identidad: sin `409`. Única identidad: `409` con `old_login_code` y `new_login_code`. Código repetido en destino: `422`. |
| Import v1 | Mismo resultado que la migración de Fase 1 sobre las mismas filas. |
| Import v2 | Crea clientes y bases; identidad distinta se reporta y no se aplica. |
| Export → import ida y vuelta | Estructura idéntica en una instalación vacía. |
| Consumo por cliente | Un turno de un agente de A contra una base de B suma a B, no a A. |
| Sin contraseñas | Ningún response de `/admin/erp-clients` ni de los endpoints nuevos contiene la contraseña, ni en claro ni cifrada (extiende el test existente). |
