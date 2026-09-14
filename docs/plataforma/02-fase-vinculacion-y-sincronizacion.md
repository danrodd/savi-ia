# Fase 2 — Vinculación y sincronización con SAVI Cloud

> Parte de: [PRD — Plataforma SAVI](00-prd.md)
> Estado: **propuesta**.
> Depende de: [Fase 1](01-fase-savi-servidor.md).
> Alcance: módulo nuevo `cloud_link` en `backend/`, pantalla de
> administración en `frontend/`, contrato en `contracts/sync/v1/`,
> esqueleto de `cloud/backend/` (API y BD) e instalador.
> La consola web de Cloud es la [Fase 3](03-fase-consola-cloud.md). En
> esta fase, clientes y tokens se crean con un comando de administración.

## Resultado esperado

- [ ] Contrato `sync/v1` versionado (JSON Schema + fixtures), validado por los dos extremos.
- [ ] `cloud/backend`: FastAPI + Postgres con clientes, instancias, tokens, heartbeats y eventos.
- [ ] Vinculación con token de un solo uso → `instance_id` + secreto.
- [ ] Heartbeat cada 5 minutos, con política y estado de la instancia en la respuesta.
- [ ] Sincronización incremental de 5 streams con marca de agua, relectura e idempotencia.
- [ ] Sin conexión: cero impacto en el chat, con recuperación completa al reconectar.
- [ ] Rotación de secreto, suspensión, revocación y detección de clones.
- [ ] Administración → **SAVI Cloud** en la instancia, con pantalla de transparencia.
- [ ] Test E2E de reconciliación: totales locales = totales en Cloud después de un corte.

---

## 1. Decisiones

| # | Decisión | Por qué |
|---|---|---|
| S1 | **Cloud vive en el monorepo** (`cloud/backend`, `cloud/frontend`) y el contrato en `contracts/sync/v1/` | Un cambio de contrato toca los dos extremos en un solo PR, con los mismos gates y skills. Se despliegan por separado. |
| S2 | **Extracción por marca de agua sobre las tablas existentes**, sin outbox | Los writers del chat usan sessionmaker independiente y sobreviven a la cancelación (`savi-backend-patterns`). Instrumentar cada escritura con un outbox tocaría ese flujo crítico. Leer las tablas no lo toca, y las tablas **ya son** el buffer durable si Cloud no responde. |
| S3 | **Relectura de 15 minutos por ciclo + idempotencia en Cloud** | Un writer puede confirmar un mensaje con `created_at` anterior a la marca ya avanzada (R6 del PRD). Releer la ventana y deduplicar por `(instance_id, stream, source_id)` garantiza que no se pierde nada. |
| S4 | **Bearer con secreto de 256 bits sobre TLS**, guardado como hash SHA-256 en Cloud | Suficiente con TLS obligatorio y rotación. HMAC por request agrega complejidad sin mitigar un riesgo real en este canal. SHA-256 alcanza para un secreto aleatorio de alta entropía, que no es una contraseña humana. |
| S5 | **Seudónimo de usuario con HMAC** y clave que nunca sale de la instancia | Cloud cuenta usuarios activos y los distingue, sin saber quiénes son (P2 del PRD). |
| S6 | **Sin contenido, nunca** | Lista blanca de campos por stream y test que la hace cumplir (RNF-04). |
| S7 | **Cloud nunca llama a la instancia** | Todo lo que Cloud necesita comunicar viaja en la respuesta del heartbeat. |
| S8 | **Un sincronizador por proceso, protegido con lock de BD** | Evita envíos concurrentes si alguien corre dos procesos sobre el mismo Postgres (escritorio con BD compartida). |

## 2. Contrato `contracts/sync/v1/`

```
contracts/sync/v1/
├── README.md                 # reglas de evolución del contrato
├── enroll.request.schema.json
├── enroll.response.schema.json
├── heartbeat.request.schema.json
├── heartbeat.response.schema.json
├── ingest.request.schema.json
├── ingest.response.schema.json
├── events/
│   ├── turn.schema.json
│   ├── conversation.schema.json
│   ├── session.schema.json
│   ├── free_query.schema.json
│   └── database.schema.json
└── fixtures/                 # ejemplos válidos e inválidos, usados por los tests de ambos lados
```

Reglas de evolución (`README.md`):

- **Compatible dentro de v1:** agregar campos opcionales o nuevos
  streams. Cloud ignora los campos que no conoce e informa como
  `rejected` los streams desconocidos, sin fallar el lote.
- **Incompatible:** renombrar, quitar o cambiar tipos. Obliga a `v2`.
  Cloud mantiene `v1` activo al menos 12 meses.
- Cada evento lleva `"schema": "turn/1"`.
- Los modelos Pydantic de cada lado se escriben a mano. Un test de
  contrato valida los fixtures contra el JSON Schema **y** contra el
  modelo, en los dos proyectos.

## 3. API de SAVI Cloud (`/api/v1`)

Base: `SAVI_CLOUD_URL`, por ejemplo `https://cloud.<dominio-seo>` (P3).
Todo en JSON UTF-8. `ingest` acepta `Content-Encoding: gzip`. Errores con
el mismo formato del backend de SAVI: `{"errorCode", "message"}`.

### 3.1 `POST /api/v1/enrollments/redeem`: vincular

Sin autenticación. Protegido por el token, con límite de 10 intentos por
IP cada 15 minutos.

```json
// request
{
  "token": "svk_enr_3Qy…",                 // 32 bytes aleatorios, base62, prefijo legible
  "instance": {
    "name": "SRV-FARMX",
    "deployment_mode": "server",
    "version": "v1.2.0",
    "commit": "2ce0b85",
    "os": "Windows Server 2022 10.0.20348",
    "agent_db_engine": "postgresql",
    "fingerprint": "b64url(sha256(machine_guid + install_id))"
  }
}
// 201 response
{
  "instance_id": "8f0c…",
  "instance_secret": "svk_ins_Zk9…",        // se muestra UNA vez; Cloud guarda sha256
  "client": { "id": "…", "code": "FARMX", "name": "Farmacias X" },
  "policy": { "heartbeat_seconds": 300, "ingest_seconds": 300, "max_batch_events": 500, "sync_enabled": true }
}
```

| Error | Status | `errorCode` |
|---|---|---|
| Token inexistente, vencido o ya usado | `404` | `enrollment_token_invalid` (un solo código, para no revelar cuál caso es) |
| Cliente suspendido | `403` | `client_suspended` |
| Límite de intentos | `429` | `too_many_requests` + `Retry-After` |

Canjear el token y crear la instancia ocurren en **una transacción**, con
`SELECT … FOR UPDATE` sobre el token. Dos canjes simultáneos del mismo
token no crean dos instancias.

### 3.2 `POST /api/v1/instances/heartbeat`

`Authorization: Bearer <instance_secret>`

```json
// request
{
  "sent_at": "2026-09-14T15:00:00Z",
  "fingerprint": "…",
  "version": "v1.2.0",
  "commit": "2ce0b85",
  "deployment_mode": "server",
  "started_at": "2026-09-14T08:00:00Z",
  "tls": true,
  "llm": { "provider": "claude", "model": "claude-sonnet-4-6", "credential_kind": "api_key", "usable": true },
  "erp_databases": { "total": 3, "usable": 3, "credentials_unreadable": 0 },
  "active_sessions": 12,
  "sync": {
    "streams": { "turn": { "watermark_at": "2026-09-14T14:58:10Z", "last_ok_at": "2026-09-14T14:58:20Z" } },
    "last_error": null
  },
  "warnings": ["http_without_tls"]
}
// 200 response
{
  "server_time": "2026-09-14T15:00:01Z",
  "instance_status": "active",               // active | suspended | revoked
  "policy": { "heartbeat_seconds": 300, "ingest_seconds": 300, "max_batch_events": 500, "sync_enabled": true },
  "notices": [
    { "code": "update_available", "severity": "info", "message": "Hay una versión nueva de SAVI: v1.3.0." }
  ],
  "ai": null                                  // se completa en la Fase 5
}
```

- `warnings` son los `code` de `server-status` (Fase 1 §8.2), sin detalle.
- Cloud guarda el último heartbeat completo en `instances.last_heartbeat`,
  más una fila en `heartbeats` (retención de 30 días).
- **Desfase de reloj:** Cloud calcula `server_time - sent_at` y alerta en
  la consola si supera 5 minutos (R5).
- **Clon (R7):** si llega un `fingerprint` distinto al registrado,
  `instance_status = "suspended"` con `notice` `fingerprint_mismatch`. Un
  administrador de Cloud confirma "Es la misma máquina" (actualiza la
  huella) o revoca.

| Error | Status | `errorCode` | Qué hace la instancia |
|---|---|---|---|
| Secreto inválido | `401` | `instance_unauthorized` | Estado `unauthorized`. Deja de sincronizar y avisa en Administración. |
| Instancia revocada | `401` | `instance_revoked` | Estado `revoked`. Deja de sincronizar y borra el secreto local. |

### 3.3 `POST /api/v1/instances/ingest`

`Authorization: Bearer`, `Content-Encoding: gzip`. Tamaño máximo
descomprimido: 5 MB; máximo 500 eventos.

```json
// request
{
  "batch_id": "0b8e…",                        // uuid4 por lote; reenvío = mismo batch_id
  "sent_at": "2026-09-14T15:00:05Z",
  "events": [
    { "schema": "turn/1", "source_id": "c1f…", "occurred_at": "2026-09-14T14:57:02Z", "data": { } }
  ]
}
// 200 response
{ "accepted": 498, "duplicates": 2, "rejected": [ { "source_id": "…", "reason": "unknown_schema" } ] }
```

- Idempotencia de **lote**: `ingest_batches(instance_id, batch_id)`. Un
  lote repetido devuelve la respuesta original sin reprocesar.
- Idempotencia de **evento**: `ON CONFLICT (instance_id, source_id) DO
  NOTHING` en la tabla del stream. Cuenta como `duplicates`.
- Un evento inválido se informa en `rejected` y **no** falla el lote. El
  lote falla con `422` solo si el sobre es inválido.
- Instancia `suspended`: `200` con `accepted = 0` y los eventos
  **no se guardan**, pero la instancia **no** avanza su marca (§5.4). Así
  no se pierde nada si luego se reactiva.

| Error | Status | `errorCode` |
|---|---|---|
| Lote demasiado grande | `413` | `batch_too_large` |
| Sobrecarga | `429` / `503` | `too_many_requests` / `unavailable` + `Retry-After` |

### 3.4 `POST /api/v1/instances/credentials/rotate`

`Authorization: Bearer <secreto actual>` → `200 {"instance_secret": "…"}`.
El secreto anterior sigue válido **24 horas**, para que un corte a mitad
de la rotación no deje la instancia afuera. La instancia guarda el nuevo
**antes** de confirmar la rotación en su log.

La instancia rota automáticamente cada 90 días, y cuando la consola lo
pide con `notice` `rotate_credentials`.

## 4. Streams y esquemas de eventos

Campos comunes de todo evento: `schema`, `source_id` (id de la fila
origen) y `occurred_at` (`created_at` de la fila, UTC).

Referencias seudónimas:

| Campo | Cálculo |
|---|---|
| `user_ref` | `hex(HMAC-SHA256(pseudonym_key, f"{erp_database_id}:{user_id}"))[:32]` |
| `database_ref` | `erp_databases.id` (UUID, no sensible) |
| `conversation_ref` | `conversations.id` |

`pseudonym_key`: 32 bytes aleatorios generados al vincular. Se guardan
cifrados en la instancia y **nunca** se envían. Si la instancia se
desvincula y se vuelve a vincular, **se conserva** la clave, para que
los mismos usuarios mantengan su seudónimo.

### 4.1 `turn/1`: un turno del asistente

Origen: `messages` con `role = 'assistant'`. Incluye los superseded y los
de conversaciones borradas, con el mismo criterio que `usage_repository`
("esos tokens se pagaron de verdad").

| Campo | Tipo | Origen |
|---|---|---|
| `conversation_ref` | uuid | `messages.conversation_id` |
| `database_ref` | uuid \| null | `conversations.erp_database_id` |
| `user_ref` | string | `conversations.owner_erp_database_id` + `user_id` |
| `provider` | string \| null | `messages.provider` |
| `model` | string \| null | `messages.model` |
| `finish_reason` | string \| null | `messages.finish_reason` |
| `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | int | claves de `messages.usage` (las mismas que `sqlalchemy_usage_repository.py:60`). Faltante = 0. |
| `cost_usd` | string decimal \| null | `messages.cost_usd` (string para no perder precisión) |
| `tools` | `[{name, status, tipo?}]` | `messages.tool_invocations`: **solo** `name`, `status` y, para `consultar_conocimiento`, `input.tipo` si pertenece a la lista blanca de tipos. **Nunca** el resto de `input`. |
| `latency_ms` | int \| null | `created_at` del asistente menos el del user activo inmediatamente anterior de la misma conversación. `null` si no se encuentra. |
| `action` | string \| null | `send`, `edit_last` o `regenerate`, si se puede inferir de `superseded_by_id`. Si no, `null`. |

### 4.2 `conversation/1`

Origen: `conversations`. Campos: `conversation_ref`, `database_ref`,
`user_ref`. Sin título: el título se genera del contenido.

### 4.3 `session/1`: inicio de sesión

Origen: `refresh_tokens.created_at`. Campos: `user_ref`,
`database_ref`. `source_id` = `jti`. Mide usuarios que entran,
independientemente de si chatean.

### 4.4 `free_query/1`

Origen: `audit_query`. Campos: `conversation_ref`, `database_ref`,
`result`, `estimated_rows`, `returned_rows` y `duration_ms`. **Nunca**
`sql`, `user_question` ni `error_message` (pueden contener literales con
datos del ERP).

### 4.5 `database/1`: inventario de sucursales (snapshot)

No es incremental. Se envía **una vez por día** y cuando cambia la lista
de bases. `source_id` = `f"{erp_database_id}:{fecha UTC}"`, así que es
idempotente por día. Campos: `database_ref`, `code`, `name`, `is_active`,
`is_usable`, `credentials_unreadable` y `last_connection_ok_at`. **Nunca**
host, puerto, usuario ni nombre físico de la base.

> **Por qué `name` y `code` sí:** la consola necesita mostrar "Sede
> Norte" y no un UUID. Son etiquetas que pone el administrador, no datos
> del ERP. Si P2/P8 lo prohíben, se envía solo `code`.

## 5. Sincronizador en la instancia

### 5.1 Módulo `app/modules/cloud_link/`

```
cloud_link/
├── domain/
│   ├── entities/cloud_link_state.py        # estado de vinculación (singleton)
│   ├── entities/stream_watermark.py
│   ├── value_objects/link_status.py        # unlinked | linked | offline | suspended | revoked | unauthorized
│   ├── interfaces/cloud_api.py             # puerto: enroll, heartbeat, ingest, rotate
│   ├── interfaces/event_source.py          # puerto: un extractor por stream
│   ├── interfaces/cloud_link_repository.py
│   └── exceptions.py
├── application/
│   ├── use_cases/link_instance.py
│   ├── use_cases/unlink_instance.py
│   ├── use_cases/send_heartbeat.py
│   ├── use_cases/sync_streams.py
│   ├── use_cases/rotate_credentials.py
│   ├── use_cases/preview_payload.py        # pantalla de transparencia
│   └── pseudonymizer.py
└── infrastructure/
    ├── http/routes.py                      # /admin/cloud-link/*
    ├── http_cloud_api.py                   # httpx.AsyncClient
    ├── sources/{turn,conversation,session,free_query,database}_source.py
    ├── persistence/models.py, repository.py
    └── scheduler.py                        # tarea de fondo del lifespan
```

Las tools MCP no cambian.

### 5.2 Tablas nuevas (BD del agente)

**`cloud_link`**, una sola fila:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `Integer` PK | Siempre `1`. `CHECK (id = 1)`. |
| `cloud_url` | `String(255)` | |
| `instance_id` | `UuidType` NULL | |
| `client_code` / `client_name` | `String` NULL | Para mostrar. |
| `secret_encrypted` | `Text` NULL | Fernet con `ERP_CREDENTIALS_KEY`. |
| `pseudonym_key_encrypted` | `Text` NOT NULL | Se genera en el primer arranque del módulo, **antes** de vincular. |
| `install_id` | `UuidType` NOT NULL | Aleatorio al crear la fila. Parte del `fingerprint`. |
| `status` | `String(16)` | Ver `LinkStatus`. |
| `policy` | `JsonType` | Última política recibida. |
| `notices` | `JsonType` | Últimos avisos de Cloud. |
| `linked_at`, `last_heartbeat_ok_at`, `last_attempt_at`, `secret_rotated_at` | `UtcDateTime` NULL | |
| `last_error_code` | `String(64)` NULL | Sin mensajes libres que puedan filtrar datos. |
| `consecutive_failures` | `Integer` | Para el backoff. |

**`cloud_sync_watermarks`**:

| Columna | Tipo |
|---|---|
| `stream` | `String(32)` PK |
| `watermark_at` | `UtcDateTime` NOT NULL |
| `watermark_id` | `String(64)` NOT NULL |
| `last_ok_at` | `UtcDateTime` NULL |

Migración Alembic con registro en `bootstrap.py` y `alembic/env.py`.
Índices que el extractor necesita y hoy **no** existen, a verificar con
`EXPLAIN` antes de crearlos: `messages (created_at, id)`,
`conversations (created_at, id)`, `refresh_tokens (created_at, jti)` y
`audit_query (created_at, id)`.

### 5.3 Ciclo de sincronización (`SyncStreamsUseCase`)

Corre cada `policy.ingest_seconds`, solo si `status ∈ {linked, offline}`
y `policy.sync_enabled`:

```
para cada stream incremental (turn, conversation, session, free_query):
    wm = watermark(stream)                   # la marca inicial se fija al vincular (§5.5)
    cursor = (wm.at - 15 min, "")                                     # relectura (S3)
    max_visto = wm
    repetir:
        filas = SELECT … WHERE (created_at, id) > cursor
                ORDER BY created_at, id LIMIT policy.max_batch_events
        si no hay filas: salir
        eventos = mapear(filas)                                       # lista blanca (S6)
        respuesta = ingest(batch_id=uuid4(), eventos)                 # reintentos: §5.6
        si falla: abortar el stream sin mover la marca
        cursor = (última.created_at, última.id)
        max_visto = max(max_visto, cursor)
    guardar watermark(stream) = max_visto, last_ok_at = now
```

- **Paginación por keyset** `(created_at, id)`: evita el bucle infinito
  que produciría un `OFFSET` o un `>=` cuando hay más filas con el mismo
  `created_at` que el tamaño del lote.
- **Comparación de tuplas portable:** `created_at > :at OR (created_at =
  :at AND id > :id)`. SQLite no garantiza la sintaxis `(a, b) > (x, y)`
  en todas sus versiones.
- La relectura reenvía, por ciclo, como máximo los eventos de los últimos
  15 minutos. Cloud los cuenta como `duplicates`.
- Si Cloud aceptó un lote pero la respuesta se perdió, el reintento usa
  **el mismo** `batch_id` y Cloud devuelve la respuesta original (§3.3,
  §5.6).
- Stream `database`: se calcula un hash del inventario y se envía si
  cambió o si pasaron 24 horas desde el último envío.

### 5.4 Suspensión

Con `instance_status = "suspended"`: el heartbeat continúa, `ingest` se
detiene y las marcas **no** se mueven. Al reactivarse, se retoma desde
donde quedó, sin pérdida.

### 5.5 Primera vinculación: qué se envía

**Por defecto se envía el historial completo**: la marca inicial es la
fecha mínima (`1970-01-01`). La consola necesita el consumo previo para
analizar al cliente desde el primer día.

- Con historial grande, el ciclo lo envía en lotes de 500 sin bloquear
  nada: son lecturas por índice en segundo plano (RNF-07).
- Opción en la pantalla de vinculación: **"Enviar solo desde hoy"**. Pone
  la marca inicial en `now()`, para empresas que no autorizan el
  histórico (P8).

### 5.6 Reintentos y backoff

| Caso | Acción |
|---|---|
| Error de red, `5xx`, `429` | Reintento del **mismo** request (mismo `batch_id`) con backoff `min(30 s × 2^n, 30 min)` ± 20% de jitter. Si hay `Retry-After`, se respeta. |
| `401 instance_unauthorized` | `status = unauthorized` y se detiene todo salvo el heartbeat, que reintenta cada 1 hora por si fue un error transitorio de Cloud. |
| `401 instance_revoked` | `status = revoked`, se borra `secret_encrypted` y se detiene todo. |
| `413` | Se reintenta ese stream con la mitad del tamaño de lote (mínimo 50). |
| `422` en el sobre | Se registra `last_error_code = contract_rejected` y se detiene el stream **sin** mover la marca. Es un bug de contrato y se ve en Administración y en la consola. |
| Sin respuesta de heartbeat por 15 min | `status = offline`. Vuelve a `linked` en el primer heartbeat exitoso. |

Timeouts de `httpx`: conexión 10 s, lectura 30 s. `trust_env=True` para
respetar `HTTPS_PROXY` corporativo (RNF-02). Validación TLS siempre
activa; `http://` solo si `APP_ENV=development`.

### 5.7 Scheduler

- Arranca en el `lifespan` (`main.py:74`) **después** de
  `init_active_provider_resolver`, como `asyncio.Task`. Se cancela y
  espera en el `finally` antes de `close_engine_registry`.
- Una excepción no controlada en un ciclo se loguea con stack y el
  scheduler **sigue**. Nunca tumba la aplicación (RNF-05).
- **Lock (S8):** en Postgres, `pg_try_advisory_lock(hashtext('savi_cloud_sync'))`
  por ciclo. Si no se obtiene, se omite el ciclo. En SQLite no hace
  falta, porque solo hay un proceso.
- `SAVI_CLOUD_SYNC_ENABLED=false` en `.env` lo apaga por completo
  (tests, desarrollo).

## 6. Vinculación desde la instancia

### 6.1 API de administración (`SaviAdminDep`)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/admin/cloud-link` | Estado: `status`, `client_name`, `instance_id`, `linked_at`, `last_heartbeat_ok_at`, marcas por stream, `last_error_code`, `notices`. Sin secretos. |
| `POST` | `/admin/cloud-link` | Body `{token, history: "all" \| "from_now"}`. Llama a `enroll`. `201` con el estado. `422` si ya está vinculada ("desvinculá primero"). Errores de Cloud mapeados (§3.1). |
| `DELETE` | `/admin/cloud-link` | Desvincula **localmente**: borra secreto e `instance_id` y detiene la sincronización. Conserva `pseudonym_key` e `install_id`. `204`. La instancia sigue existiendo en Cloud hasta que la revoquen desde la consola. |
| `POST` | `/admin/cloud-link/sync-now` | Dispara heartbeat + ciclo inmediatamente. `202`. |
| `GET` | `/admin/cloud-link/preview` | Transparencia: el último heartbeat enviado y **un evento real** por stream, exactamente como viajaría. |

### 6.2 Instalador

- Página "Conectar con SAVI Cloud" (modos Servidor y Escritorio): campo
  de token, opcional, con el texto "Te lo entrega SEO Group. Podés
  hacerlo después desde Administración."
- Escribe `SAVI_CLOUD_URL` (fija, la de producción) y
  `SAVI_CLOUD_ENROLLMENT_TOKEN`. Al arrancar, si hay token y la instancia
  no está vinculada, SAVI vincula y **vacía** la variable del `.env`
  (en modo servicio tiene permisos). Si falla, queda el aviso en
  Administración y el token se puede reintentar desde la interfaz.

### 6.3 Frontend: Administración → SAVI Cloud

`/admin/cloud` (`admin-cloud`), ícono `CloudUpload`:

- **No vinculada:** campo de token, opción de historial (§5.5) y botón
  "Vincular".
- **Vinculada:** cliente, estado con color (`linked` verde, `offline`
  ámbar, `suspended`/`unauthorized`/`revoked` rojo), último contacto,
  estado por stream ("Turnos: al día" / "enviando historial…"), avisos de
  Cloud, y botones "Sincronizar ahora" y "Desvincular" (con
  confirmación).
- **"Qué datos se envían":** panel que muestra `/preview` en JSON
  legible, con la explicación de cada campo y de lo que **no** se envía
  (preguntas, respuestas, SQL, datos del ERP, nombres de usuario).
- Aviso global en `AdminLayout` si el estado es `offline` hace más de 72
  horas (P6), `suspended`, `unauthorized` o `revoked`.

## 7. SAVI Cloud: esqueleto de backend

### 7.1 Estructura

`cloud/backend/`, mismo stack y skills que `backend/`
(`enterprise-backend-fastapi`): FastAPI, SQLAlchemy 2 async, Alembic,
Pydantic v2, uv, Ruff y Pyright strict. **Solo Postgres.**

```
cloud/backend/app/modules/
├── clients/        # clientes (empresas)
├── instances/      # instancias, heartbeats, credenciales, huellas
├── enrollment/     # tokens de vinculación
├── ingest/         # recepción, validación e idempotencia de eventos
└── metrics/        # agregados diarios (consumidos por la Fase 3)
```

### 7.2 Modelo de datos (Postgres Cloud)

**`clients`**: `id`, `code` (único), `name`, `nit` NULL, `status`
(`active`/`suspended`), `created_at`, `updated_at`.

**`instances`**:

| Columna | Notas |
|---|---|
| `id` UUID PK | `instance_id` |
| `client_id` FK | |
| `name`, `deployment_mode`, `os`, `agent_db_engine` | Del enroll y del último heartbeat |
| `version`, `commit` | Del último heartbeat |
| `status` | `active` / `suspended` / `revoked` |
| `status_reason` | `manual`, `fingerprint_mismatch`… |
| `secret_hash` BYTEA | SHA-256 |
| `previous_secret_hash` BYTEA NULL, `previous_secret_expires_at` | Rotación (§3.4) |
| `fingerprint` | |
| `enrolled_at`, `last_seen_at`, `last_heartbeat` JSONB, `clock_skew_seconds` | |

Índice único sobre `secret_hash`. La autenticación busca por hash del
bearer recibido, con comparación en tiempo constante del hash encontrado.

**`enrollment_tokens`**: `id`, `client_id`, `token_hash` (único),
`expires_at` (default 72 h), `used_at`, `used_by_instance_id`,
`revoked_at`, `created_by`, `created_at`.

**`heartbeats`**: `instance_id`, `received_at`, `payload` JSONB.
Particionada por mes; retención de 30 días con un job diario.

**`ingest_batches`**: PK `(instance_id, batch_id)`, `received_at`,
`accepted`, `duplicates`, `rejected` JSONB. Retención de 7 días (solo
sirve para reintentos).

**Tablas de eventos tipadas**, una por stream. Todas con PK `(instance_id,
source_id)`, `client_id` desnormalizado y `occurred_at`, particionadas por
mes con retención de 13 meses:

| Tabla | Columnas propias |
|---|---|
| `ev_turns` | `conversation_ref`, `database_ref`, `user_ref`, `provider`, `model`, `finish_reason`, 4 contadores de tokens, `cost_usd NUMERIC(12,6)`, `tools JSONB`, `latency_ms`, `action` |
| `ev_conversations` | `conversation_ref`, `database_ref`, `user_ref` |
| `ev_sessions` | `user_ref`, `database_ref` |
| `ev_free_queries` | `conversation_ref`, `database_ref`, `result`, `estimated_rows`, `returned_rows`, `duration_ms` |
| `instance_databases` | `database_ref`, `code`, `name`, estado, `snapshot_date`. PK `(instance_id, database_ref, snapshot_date)` |

**Por qué tablas tipadas y no una tabla JSONB genérica:** la consola
agrega por cliente, día, modelo y usuario sobre millones de filas.
Columnas tipadas e índices `(client_id, occurred_at)` hacen esas
consultas baratas. El JSONB genérico obligaría a extraer y castear en
cada consulta.

**`daily_client_metrics`** (Fase 3 la consume, pero se crea acá para
validar la reconciliación): `client_id`, `day` (zona
`America/Bogota`), `turns`, `conversations`, `sessions`,
`active_users`, 4 tokens, `cost_usd`, `turns_with_error` y
`free_queries_failed`. Se recalcula con un job incremental cada 15
minutos para los días tocados por eventos nuevos.

### 7.3 Comandos de administración (hasta la Fase 3)

```powershell
uv run cloud-admin client create --code FARMX --name "Farmacias X"
uv run cloud-admin token create --client FARMX --expires-hours 72   # imprime el token una vez
uv run cloud-admin instance list --client FARMX
uv run cloud-admin instance suspend|activate|revoke <instance_id>
```

### 7.4 Operación mínima

- Despliegue con contenedor, Postgres administrado y TLS terminado por el
  proveedor (P3).
- `GET /health` (sin BD) y `GET /ready` (con BD).
- Logs JSON estructurados, sin bearer ni payloads.
- Límites: 60 requests/min por instancia en `heartbeat`, 30/min en
  `ingest`. `429` con `Retry-After`.

## 8. Tests

### 8.1 Contrato (los dos proyectos)

- Todos los fixtures válidos pasan el JSON Schema y el modelo Pydantic
  del proyecto; todos los inválidos fallan en los dos.
- **Test de privacidad (RNF-04):** recorre los JSON Schema de `events/` y
  falla si aparece un campo fuera de la lista blanca aprobada, o uno cuyo
  nombre contenga `sql`, `question`, `content`, `answer`, `password`,
  `host`, `login` o `full_name`.

### 8.2 Instancia (pytest)

| Test | Verifica |
|---|---|
| Mapeo `turn` | Tokens desde `usage`, `cost_usd` como string, `tools` sin `input` salvo `tipo` en lista blanca, `latency_ms` calculado. |
| Seudónimo | Estable para el mismo `(base, usuario)`; distinto entre bases; se conserva tras desvincular y revincular. |
| Keyset | 1.200 filas con el mismo `created_at` y lote de 500 → 3 lotes, sin repetir ni saltear. |
| Relectura | Un mensaje insertado con `created_at` 5 minutos antes de la marca se envía en el ciclo siguiente. |
| Fallo a mitad | Error en el lote 2 → la marca no se mueve y el reintento usa el mismo `batch_id`. |
| Backoff | Secuencia de esperas con jitter acotado y respeto de `Retry-After`. |
| Estados | `401 revoked` borra el secreto; `suspended` no mueve marcas; 15 minutos sin heartbeat → `offline`. |
| Aislamiento del chat | Con `CloudApi` fake que cuelga o levanta, un turno completo del chat no cambia su duración ni su resultado. |
| Lock | Dos ciclos concurrentes sobre Postgres: solo uno envía. |
| API admin | `403` sin admin; ningún response contiene `secret` ni `pseudonym_key`; `preview` coincide con lo que envía el ciclo. |
| Instalador | El token del `.env` se canjea y se vacía; un token inválido deja el aviso y no reintenta en bucle. |

### 8.3 Cloud (pytest)

| Test | Verifica |
|---|---|
| Enroll | Token de un solo uso; dos canjes concurrentes crean una sola instancia; vencido, usado e inexistente devuelven el mismo `404`. |
| Auth | Secreto actual y anterior (dentro de 24 h) válidos; anterior vencido `401`; revocada `401 instance_revoked`. |
| Idempotencia | Lote repetido → misma respuesta; evento repetido en otro lote → `duplicates`. |
| Rechazo parcial | Un evento inválido no descarta los válidos del lote. |
| Suspensión | `ingest` no persiste y responde `accepted = 0`. |
| Huella | Huella distinta suspende con `fingerprint_mismatch`. |
| Agregado diario | Recalcula solo los días afectados; usa la zona `America/Bogota`. |

### 8.4 E2E de reconciliación (criterio de cierre)

1. Levantar Cloud y una instancia de prueba con Postgres, vinculadas.
2. Generar 30 turnos reales o sembrados, con 2 usuarios en 2 bases.
3. Cortar la red de la instancia hacia Cloud (bloqueo de puerto) y
   generar 20 turnos más.
4. Restaurar la red y esperar dos ciclos.
5. **Verificar:** en Cloud, los tokens totales, `cost_usd` y usuarios
   activos del período son **iguales** a los de `/usage/system` de la
   instancia. Cero duplicados en `ev_turns`.
