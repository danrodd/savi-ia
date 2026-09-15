# Fase 1 — Modelo de clientes y migración

> Parte de: [PRD — Clientes con varias bases](00-prd.md)
> Estado: **propuesta**.
> Cambio visible: **ninguno**. Al terminar, el sistema se comporta igual
> que hoy, pero cada base ya pertenece a un cliente.

## Resultado esperado

- [ ] Tabla `erp_clients` creada, con índices únicos parciales.
- [ ] `erp_databases` con `client_id` (FK) e `is_identity`, sin `is_default`.
- [ ] Migración con backfill (un cliente por base, mismo código) y `downgrade` real.
- [ ] Modelo registrado en `bootstrap.py` y en `alembic/env.py`.
- [ ] Entidad `ErpClient`, puerto `ErpClientRepository` e implementación SQLAlchemy.
- [ ] Seed desde `.env` que crea cliente + base de identidad.
- [ ] Todos los consumidores de `get_default` / `get_by_code` adaptados (§5).
- [ ] Suite actual en verde, sin cambiar ningún test de comportamiento.

---

## 1. Por qué esta fase va sola

Es la de mayor superficie tocada (esquema, migración, repositorios,
seed) y **no cambia ningún comportamiento**. Si algo se rompe acá, se
nota sin el ruido de las reglas de acceso nuevas. El mismo criterio usó
la Fase 1 de multi-BD.

## 2. Modelo de datos

### 2.1 Tabla nueva `erp_clients` (en `agent_db`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `UuidType` PK | |
| `code` | `String(32)` NOT NULL | Lo que va después del `@` en el login. Mismo formato que hoy: `^[A-Z0-9_-]{2,32}$`, normalizado con `normalize_code`. |
| `name` | `String(120)` NOT NULL | Nombre visible de la empresa. |
| `is_default` | `Boolean` NOT NULL, default `false` | Cliente del login sin `@`. Uno solo entre los no eliminados. |
| `is_active` | `Boolean` NOT NULL, default `true` | |
| `deleted_at` | `UtcDateTime` NULL | Baja lógica. |
| `created_at` / `updated_at` | `UtcDateTime` NOT NULL | Igual que `erp_databases`. |

Índices, todos siguiendo el patrón de `erp_database_model.py`:

- `uq_erp_clients_code`: único parcial sobre `code WHERE deleted_at IS NULL`.
- `uq_erp_clients_name`: único parcial sobre `name WHERE deleted_at IS NULL`.
- `uq_erp_clients_default`: único parcial sobre `is_default WHERE deleted_at IS NULL AND is_default`.
- `ix_erp_clients_active`: `(deleted_at, is_active)`.

### 2.2 Cambios en `erp_databases`

| Cambio | Detalle |
|---|---|
| **+** `client_id` | `UuidType`, FK → `erp_clients.id`. NOT NULL después del backfill. |
| **+** `is_identity` | `Boolean` NOT NULL, default `false`. |
| **−** `is_default` | Se elimina, porque pasa al cliente (C4). |
| Índice `uq_erp_databases_code` | Pasa de global a **por cliente**: `(client_id, code) WHERE deleted_at IS NULL`. |
| Índice `uq_erp_databases_name` | Pasa a **por cliente**: `(client_id, name) WHERE deleted_at IS NULL`. Dos empresas pueden tener una sucursal "Centro". |
| **−** `uq_erp_databases_default` | Se elimina. |
| **+** `uq_erp_databases_identity` | Único parcial sobre `client_id WHERE deleted_at IS NULL AND is_identity`. Hay una sola identidad por cliente. |
| **+** `ix_erp_databases_client` | `(client_id, deleted_at, is_active)`, para listar las bases de un cliente. |

**Por qué el código de base sigue existiendo (C2):** el export/import
empareja las filas por código (`export_import_erp_databases.py:168`), y
el SaaS del paso 3 va a necesitar un identificador estable de la
sucursal que no dependa del UUID de cada instalación.

**Por qué `is_identity` con flag y no `erp_clients.identity_database_id`:**
es el mismo patrón que ya usa `is_default` con índice único parcial. Una
FK desde el cliente hacia la base crea un ciclo
(`clients → databases → clients`), que complica el orden de inserción y
el batch mode de SQLite.

### 2.3 Invariantes que el esquema no puede expresar

Se validan en la capa de aplicación (Fase 3). Esta fase solo las deja
documentadas en la entidad:

- Un cliente activo con al menos una base no eliminada tiene
  **exactamente una** base de identidad.
- La base de identidad no puede estar eliminada mientras el cliente tenga
  otras bases.
- El cliente predeterminado no puede estar inactivo ni eliminado.

## 3. Dominio

### 3.1 Entidad `ErpClient`

`app/modules/erp_databases/domain/entities/erp_client.py`

```python
@dataclass
class ErpClient:
    id: UUID
    code: str
    name: str
    is_default: bool = False
    is_active: bool = True
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def is_deleted(self) -> bool: ...
    @property
    def is_usable(self) -> bool:  # not deleted and active
        ...
    def soft_delete(self) -> None: ...
```

**Por qué dentro del módulo `erp_databases` y no en un módulo nuevo
(C1):** cliente y base forman el mismo registro de conexiones y cambian
juntos. `auth` ya depende de `erp_databases`. Un módulo `clients` aparte
obligaría a `erp_databases` a importarlo para validar `client_id`, y a
`auth` a depender de los dos. Si el SaaS lo justifica, se separa en el
paso 2.

### 3.2 Cambios en `ErpDatabase`

- **+** `client_id: UUID | None = None` (`None` solo antes de persistir).
- **+** `is_identity: bool = False`.
- **−** `is_default`.
- `is_usable` **no** cambia en esta fase. La regla "base utilizable
  requiere cliente utilizable" es de acceso y va en la Fase 2 (C7). Así
  esta fase no cambia comportamiento.

### 3.3 Puerto nuevo `ErpClientRepository`

```python
class ErpClientRepository(ABC):
    async def get_by_id(self, client_id: UUID) -> ErpClient | None: ...
    async def get_by_code(self, code: str) -> ErpClient | None: ...   # excluye eliminados
    async def get_default(self) -> ErpClient | None: ...
    async def list_all(self, *, include_inactive: bool = False) -> list[ErpClient]: ...
    async def count(self) -> int: ...                                  # incluye eliminados
    async def save(self, client: ErpClient) -> None: ...
```

### 3.4 Cambios en `ErpDatabaseRepository`

| Método | Cambio |
|---|---|
| `get_default()` | **Se conserva con otro significado**: la base de identidad del cliente predeterminado. Así `main.py:98`, `connection_provider.py:47` y el factory de usuarios no cambian de contrato. |
| `get_by_code(code)` | **Se reemplaza** por dos métodos. Con códigos por cliente, "la base con código X" ya no es única. |
| **+** `get_identity_for_client_code(code)` | Base de identidad del cliente con ese código. Es la búsqueda del login. |
| **+** `get_by_client_and_code(client_id, code)` | Para export/import. |
| **+** `list_by_client(client_id, *, include_inactive=False)` | |
| **+** `count_by_client(client_id)` | Solo no eliminadas. Lo usa la Fase 3 para decidir si la primera base es la de identidad. |

La implementación SQLAlchemy resuelve `get_default` y
`get_identity_for_client_code` con un único `JOIN` a `erp_clients`, con
**los mismos filtros de hoy**: base no eliminada. Los filtros de base o
cliente inactivo los sigue aplicando quien llama (`ErpUserRepositoryFactory`
ya lo hace con `is_usable`).

## 4. Migración

Revisión nueva con `down_revision = "f2c7b9d8e1a0"` (head actual,
`add_provider_model_to_messages`). Hay que confirmarlo con
`uv run alembic heads` antes de generarla.

### 4.1 `upgrade`

A diferencia de multi-BD, **esta migración sí hace el backfill (C5)**.
Todo lo que necesita ya está en la misma BD y no depende del `.env`.

1. `create_table("erp_clients")` con sus índices.
2. `batch_alter_table("erp_databases")`: agregar `client_id` (nullable) e
   `is_identity` (default `false`).
3. Por cada fila de `erp_databases`, **incluidas las eliminadas**:
   - Insertar un `erp_clients` con `id = uuid4()` generado en Python,
     `code`, `name`, `is_active` y `deleted_at` copiados, e
     `is_default = erp_databases.is_default`.
   - `UPDATE erp_databases SET client_id = <nuevo>, is_identity = true`.
4. `batch_alter_table("erp_databases")`: `client_id` NOT NULL, crear la
   FK, borrar `is_default` y `uq_erp_databases_default`, y recrear
   `uq_erp_databases_code` / `uq_erp_databases_name` como índices
   compuestos por cliente. Crear `uq_erp_databases_identity` e
   `ix_erp_databases_client`.

Cuidados concretos:

- **UUID:** usar `sa.table(..., sa.column("id", sa.Uuid(as_uuid=True)))`
  para los `insert`/`update`. `UuidType` es `Uuid(as_uuid=True)`: en
  SQLite se guarda como `CHAR(32)` sin guiones, así que un string con
  guiones escrito a mano no coincidiría con lo que lee el ORM. No usar
  `gen_random_uuid()`, que no existe en SQLite.
- **Bases eliminadas:** su cliente nace eliminado (`deleted_at` copiado).
  Por eso no chocan con `uq_erp_clients_code`, que es parcial (R5).
- **Tabla vacía:** instalación recién actualizada que todavía no sembró.
  La migración no hace nada en el paso 3 y el seed (§6) crea cliente y
  base al arrancar.
- **Batch mode obligatorio** en los dos `alter`, por SQLite.

### 4.2 `downgrade`

1. **Verificar antes de tocar nada:** si hay dos bases no eliminadas con
   el mismo `code` en clientes distintos, levantar `RuntimeError` con
   los códigos en conflicto. Restaurar el índice global fallaría a mitad
   de camino (R6).
2. Agregar `erp_databases.is_default` y copiar `true` a la base de
   identidad del cliente predeterminado.
3. Restaurar `uq_erp_databases_code`, `uq_erp_databases_name` (globales)
   y `uq_erp_databases_default`.
4. Borrar `client_id`, `is_identity`, sus índices y la tabla `erp_clients`.

Pérdida aceptada y documentada en el docstring: la agrupación en
clientes se pierde, y cada base vuelve a ser un cliente suelto.

### 4.3 Registro del modelo

- `ErpClientModel` en `_REGISTERED_MODELS` de
  `app/infrastructure/database/bootstrap.py`, **antes** de
  `ErpDatabaseModel`, para que `create_all` respete el orden de la FK.
- Import en `alembic/env.py`.

## 5. Consumidores a adaptar

Lista cerrada, obtenida con `rg "get_default\(|get_by_code\(|is_default"`
sobre `app/`:

| Archivo | Cambio |
|---|---|
| `auth/infrastructure/persistence/erp_user_repository_factory.py:42,51` | `for_code(code)` usa `get_identity_for_client_code`. `for_code(None)` sigue con `get_default()`. |
| `erp_databases/infrastructure/connection_provider.py:47` | Sin cambio de código: `get_default()` ya devuelve la identidad del predeterminado. |
| `main.py:98` | Sin cambio de código, por la misma razón. |
| `erp_databases/infrastructure/seed.py` | Ver §6. |
| `erp_databases/application/use_cases/manage_erp_databases.py` | En esta fase, `create` crea también un cliente con el mismo código y nombre, y marca la base como identidad. Así la API actual sigue funcionando igual. `set_default` / `_forbid_if_default` operan sobre el cliente de la base. La API con cliente explícito llega en la Fase 3. |
| `erp_databases/application/use_cases/export_import_erp_databases.py` | Mismo criterio: cada fila v1 crea o actualiza un cliente con el mismo código. `get_by_code` pasa a `get_identity_for_client_code`. |
| `erp_databases/application/dtos/erp_database_dto.py` y `responses/erp_database_responses.py` | `is_default` se **calcula** (`client.is_default and base.is_identity`) para no romper el contrato con el frontend en esta fase. Se agregan `client_id` e `is_identity`. |
| `erp_databases/infrastructure/persistence/sqlalchemy_erp_database_repository.py` | Mapeo de las columnas nuevas y métodos de §3.4. |

> Si durante la implementación aparece otro consumidor, se agrega a esta
> tabla, como se hizo con el octavo consumidor en multi-BD §3.1.

## 6. Seed desde `.env`

`seed_default_database` pasa a sembrar **cliente + base**:

```
si erp_clients y erp_databases están vacías y ERP_DB_HOST tiene valor:
    cliente = ErpClient(code=<mismo cálculo de hoy>, name=<igual>, is_default=True)
    base    = erp_database_from_settings(settings) con client_id=cliente.id, is_identity=True
```

- Idempotencia: `client_repository.count() == 0 and database_repository.count() == 0`.
  Se mira también la de bases por el caso de una BD migrada a medias.
- `erp_database_from_settings` sigue siendo la única definición, porque
  la usa también el diagnóstico del launcher.

## 7. Tests

| Test | Verifica |
|---|---|
| Migración sobre SQLite existente con 2 bases activas + 1 eliminada con código repetido | 3 clientes, el eliminado nace eliminado, cada base es identidad y el predeterminado se conserva (R5). |
| Migración sobre SQLite nueva (`create_all` + `stamp head`) | Existen los 4 índices parciales de `erp_clients` y `uq_erp_databases_identity`. |
| `downgrade` con códigos de base repetidos entre clientes | Levanta antes de modificar el esquema (R6). |
| `downgrade` limpio | `is_default` restaurado en la base correcta. |
| Índice por cliente | Dos clientes pueden tener una base `CENTRO`. El mismo cliente no. |
| Índice de identidad | Una segunda base de identidad en el mismo cliente viola el índice. |
| Seed | Crea cliente predeterminado + base de identidad. No corre si hay filas (incluidas eliminadas). |
| `get_identity_for_client_code` | Resuelve la identidad, ignora bases no identidad del mismo cliente y clientes eliminados. |
| Regresión | `tests/unit/modules/auth/test_qualified_login.py` y `tests/unit/modules/erp_databases/*` pasan sin cambiar aserciones de comportamiento. |

Verificación final: `uv run lint`, `uv run typecheck`, `uv run pytest` y
arranque real contra `savi_agente` (Postgres) y una SQLite copiada de una
instalación, confirmando que el login `ADMIN@<code>` sigue entrando.
