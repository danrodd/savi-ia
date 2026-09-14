# Fase 3 — Consola SAVI Cloud

> Parte de: [PRD — Plataforma SAVI](00-prd.md)
> Estado: **propuesta**.
> Depende de: [Fase 2](02-fase-vinculacion-y-sincronizacion.md).
> Alcance: `cloud/backend` (autenticación del staff, API de consola,
> alertas, auditoría) y `cloud/frontend` (aplicación web nueva).

## Resultado esperado

- [ ] Autenticación del staff con contraseña (argon2id) y TOTP obligatorio.
- [ ] Roles `admin`, `soporte` y `comercial`, con matriz de permisos aplicada en backend.
- [ ] Pantallas: Resumen, Clientes, Detalle de cliente, Instancias, Detalle de instancia, Alertas, Tokens, Staff y Auditoría.
- [ ] Métricas con definición única (§4), calculadas desde `daily_client_metrics` y los eventos.
- [ ] Motor de alertas con reglas configurables y estado (abierta, reconocida, resuelta).
- [ ] Auditoría de toda acción que modifica estado.
- [ ] Reemplazo de los comandos `cloud-admin` de la Fase 2 por la interfaz (los comandos quedan para emergencias).
- [ ] Tests de permisos por endpoint y E2E del flujo "crear cliente → token → instancia vinculada visible".

---

## 1. Usuarios y roles

| Acción | `admin` | `soporte` | `comercial` |
|---|---|---|---|
| Ver resumen, clientes, instancias, métricas | ✅ | ✅ | ✅ |
| Ver detalle técnico de instancia (heartbeat, errores de sync, huella) | ✅ | ✅ | — |
| Crear y editar clientes | ✅ | — | ✅ |
| Generar y revocar tokens de vinculación | ✅ | ✅ | — |
| Suspender, activar o revocar instancia; confirmar huella; pedir rotación | ✅ | ✅ | — |
| Suspender cliente | ✅ | — | — |
| Reconocer y resolver alertas | ✅ | ✅ | — |
| Configurar reglas de alerta | ✅ | — | — |
| Administrar staff | ✅ | — | — |
| Ver auditoría | ✅ | — | — |
| Créditos y modo de IA (Fase 5) | ✅ | — | ✅ (solo lectura + recargas) |

La matriz vive en `cloud/backend/app/modules/staff/domain/permissions.py`
como un mapa `Permission → set[Role]`. Cada endpoint declara el
`Permission` que exige con una dependencia `RequirePermission(...)`.
**Nunca** se decide solo en el frontend: el frontend oculta lo que el
backend igual rechaza.

## 2. Autenticación del staff

### 2.1 Modelo

**`staff_users`**: `id`, `email` (único, minúsculas), `full_name`,
`password_hash` (argon2id), `role`, `totp_secret_encrypted` NULL,
`totp_enabled_at` NULL, `is_active`, `failed_attempts`, `locked_until`
NULL, `last_login_at`, `created_at`, `updated_at`.

**`staff_sessions`**: `jti`, `staff_user_id`, `created_at`,
`last_used_at`, `expires_at`, `revoked_at`, `ip`, `user_agent`.

### 2.2 Flujo

1. `POST /console/auth/login` `{email, password}`. Si es correcto y el
   TOTP está activo → `200 {mfa_required: true, mfa_token}`. El
   `mfa_token` es un JWT de 5 minutos con propósito `mfa`.
2. `POST /console/auth/mfa` `{mfa_token, code}` → access token (15 min) +
   refresh token (8 h, en cookie `HttpOnly; Secure; SameSite=Strict`,
   path `/console/auth`).
3. **Primer ingreso** sin TOTP configurado → `mfa_setup_required`. La
   pantalla muestra el QR (`otpauth://`) y exige confirmar un código
   antes de emitir tokens. **No existe forma de omitir el TOTP.**
4. `POST /console/auth/refresh`, `POST /console/auth/logout`.

Reglas:

- Mismo mensaje y mismo piso de duración para email inexistente y
  contraseña incorrecta (patrón de `login.py` de SAVI).
- 5 fallos → bloqueo de 15 minutos por cuenta, más límite por IP.
- TOTP: RFC 6238, 30 s, ventana ±1. Un código usado no se acepta dos
  veces (se guarda el último paso usado).
- Contraseña: mínimo 12 caracteres, verificada contra una lista local de
  contraseñas comunes.
- **Por qué refresh en cookie `HttpOnly` y no en `localStorage`** como en
  SAVI: la consola ve datos de todos los clientes y es alcanzable desde
  internet. Un XSS no debe poder robar una sesión de 8 horas. En SAVI
  Servidor el riesgo y la exposición son otros (red interna).
- Primer `admin`: `uv run cloud-admin staff create --email … --role admin`
  imprime una contraseña temporal que obliga a cambiarla y a configurar
  el TOTP en el primer ingreso.

## 3. API de consola (`/console/api`)

Todas con autenticación de staff y `RequirePermission`. Paginación
`?limit&cursor` y filtros por query. Períodos con `?start&end` (ISO
8601), por defecto los últimos 30 días, en zona `America/Bogota`.

### 3.1 Resumen

`GET /console/api/overview`:

```json
{
  "clients": { "active": 42, "suspended": 1 },
  "instances": { "online": 40, "offline": 3, "suspended": 1, "revoked": 2 },
  "period": { "start": "…", "end": "…" },
  "usage": { "turns": 51234, "conversations": 8120, "active_users": 610, "cost_usd": "1843.22", "tokens": 912345678 },
  "trend": [ { "day": "2026-09-01", "turns": 1700, "cost_usd": "61.20", "active_users": 180 } ],
  "providers": [ { "provider": "claude", "model": "claude-sonnet-4-6", "turns": 40000, "cost_usd": "1500.10" } ],
  "versions": [ { "version": "v1.1.0", "instances": 30 }, { "version": "v1.0.1", "instances": 10 } ],
  "open_alerts": { "critical": 1, "warning": 4 }
}
```

### 3.2 Clientes

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/clients` | `clients.read`. Filtros: `status`, `q` (código/nombre), `sort` (`cost`, `active_users`, `last_seen`). Cada fila: código, nombre, estado, instancias (online/total), usuarios activos 30 d, turnos 30 d, costo 30 d, última actividad, versión más antigua, alertas abiertas. |
| `POST` | `/clients` | `clients.write`. `{code, name, nit?}` |
| `GET` | `/clients/{id}` | `clients.read` |
| `PATCH` | `/clients/{id}` | `clients.write` |
| `POST` | `/clients/{id}/suspend` · `/activate` | `clients.suspend`. Suspender un cliente suspende todas sus instancias (`status_reason = client_suspended`). |
| `GET` | `/clients/{id}/metrics` | `clients.read`. Serie diaria + totales + desgloses (§4.2). |
| `GET` | `/clients/{id}/databases` | `clients.read`. Último snapshot de `instance_databases`. |
| `GET` | `/clients/{id}/users` | `clients.read`. Ranking por `user_ref`: turnos, costo, último uso, bases usadas. **Solo seudónimos.** |

### 3.3 Instancias

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/instances` | `instances.read`. Filtros: `client_id`, `status`, `connectivity` (`online`/`offline`), `version`, `outdated=true`. |
| `GET` | `/instances/{id}` | `instances.read`. Datos + último heartbeat. El detalle técnico (`fingerprint`, `sync`, `warnings`, `clock_skew_seconds`) solo con `instances.read_technical`. |
| `GET` | `/instances/{id}/heartbeats` | `instances.read_technical`. Últimos 30 días, paginado. |
| `POST` | `/instances/{id}/suspend` · `/activate` · `/revoke` | `instances.manage`. `revoke` es irreversible y pide `{confirm: "REVOCAR"}`. |
| `POST` | `/instances/{id}/confirm-fingerprint` | `instances.manage`. Acepta la huella nueva y reactiva. |
| `POST` | `/instances/{id}/request-rotation` | `instances.manage`. Agrega `notice rotate_credentials` al próximo heartbeat. |

### 3.4 Tokens de vinculación

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/clients/{id}/enrollment-tokens` | `tokens.manage`. Estado: vigente / usado (por qué instancia) / vencido / revocado. **Nunca** el token. |
| `POST` | `/clients/{id}/enrollment-tokens` | `tokens.manage`. `{expires_hours: 1..168}` → `201 {token, expires_at}`. **Única vez que se ve el token.** |
| `DELETE` | `/enrollment-tokens/{id}` | `tokens.manage`. Revoca. |

### 3.5 Alertas, staff y auditoría

- `GET /alerts?status&severity&client_id`, `POST /alerts/{id}/ack`,
  `POST /alerts/{id}/resolve` `{note}`.
- `GET /alert-rules`, `PATCH /alert-rules/{code}` `{enabled, threshold,
  severity}` (`alerts.configure`).
- `GET/POST/PATCH /staff`, `POST /staff/{id}/reset-mfa`,
  `POST /staff/{id}/deactivate` (`staff.manage`). Un admin no puede
  desactivarse a sí mismo ni dejar el sistema sin admins activos.
- `GET /audit?actor&action&target&start&end` (`audit.read`).

## 4. Métricas: definiciones únicas

Una métrica mal definida produce discusiones eternas. Estas definiciones
son **la** fuente de verdad. Viven en
`cloud/backend/app/modules/metrics/domain/definitions.py` con docstrings
idénticos a esta tabla, y la interfaz las muestra en un tooltip.

### 4.1 Definiciones

| Métrica | Definición | Fuente |
|---|---|---|
| **Turnos** | Cantidad de eventos `turn`, incluidos superseded. | `ev_turns` |
| **Conversaciones** | Eventos `conversation` creados en el período. | `ev_conversations` |
| **Usuarios activos (período)** | `user_ref` distintos con al menos un `turn` en el período. | `ev_turns` |
| **DAU** | Usuarios activos en un día calendario (`America/Bogota`). | `ev_turns` |
| **MAU** | Usuarios activos en los últimos 30 días móviles al día de cálculo. | `ev_turns` |
| **Usuarios que entran** | `user_ref` distintos con al menos una `session` en el período, tengan o no turnos. | `ev_sessions` |
| **Adopción** | Usuarios activos ÷ usuarios que entran. | derivada |
| **Tokens** | Suma de los 4 contadores. | `ev_turns` |
| **Costo (USD)** | Suma de `cost_usd`. Turnos con `cost_usd` nulo **no** se estiman: se cuentan aparte como "sin precio". | `ev_turns` |
| **Costo por usuario activo** | Costo ÷ usuarios activos. | derivada |
| **Turnos con error** | Turnos con `finish_reason = error`. Se muestran aparte `interrupted` (el usuario cortó) y `truncated` (se alcanzó el tope de caracteres), que no son errores del sistema. Valores de `MessageFinishReason` de SAVI: `complete`, `truncated`, `interrupted`, `error`. | `ev_turns` |
| **Tasa de error** | Turnos con error ÷ turnos. | derivada |
| **Latencia p50/p90** | Percentiles de `latency_ms` no nulo. | `ev_turns` |
| **Uso de tools** | Conteo por `tools[].name` y, en conocimiento, por `tipo`; tasa de `status = error`. | `ev_turns.tools` |
| **Consultas libres fallidas** | `free_query` con `result` distinto de éxito ÷ total. | `ev_free_queries` |
| **Instancia online** | `last_seen_at` hace menos de 15 minutos. | `instances` |
| **Instancia desactualizada** | Su versión es menor que la última release publicada (tag más reciente, configurado en Cloud como `latest_version`). | `instances` |
| **Frescura de datos** | Lo más atrasado entre `now - last_seen_at` y la marca más vieja de sus streams. | `last_heartbeat.sync` |

> **Frescura, visible siempre.** Toda métrica de un cliente muestra "datos
> hasta hace N min". Una instancia offline hace 2 días hace ver una caída
> de uso que no existió. La consola lo explica en lugar de dejar que
> alguien lo interprete como pérdida del cliente.

### 4.2 `GET /clients/{id}/metrics`

Totales y serie diaria desde `daily_client_metrics`. Desgloses con
consultas sobre eventos, acotadas por `(client_id, occurred_at)`:

- por modelo y proveedor (turnos, tokens, costo);
- por base/sucursal (`database_ref` → nombre del snapshot);
- uso de tools;
- distribución de `finish_reason`;
- latencia p50/p90 por día.

Rendimiento objetivo: p95 menor a 800 ms para un cliente con 1 millón de
turnos en 13 meses, con los índices `(client_id, occurred_at)` de las
tablas particionadas. Se verifica con un dataset sintético en el test de
carga (§8.3).

## 5. Alertas

### 5.1 Reglas iniciales

| `code` | Condición | Severidad | Resolución automática |
|---|---|---|---|
| `instance_offline` | Instancia `active` sin heartbeat por más de `threshold` (default 60 min) | warning; critical después de 24 h | Al volver un heartbeat |
| `instance_fingerprint_mismatch` | Suspendida por huella | critical | Al confirmar huella o revocar |
| `sync_stalled` | Una marca de stream sin avanzar por más de 6 h con instancia online y turnos locales (inferido: `active_sessions > 0`) | warning | Al avanzar |
| `contract_rejected` | `last_error_code = contract_rejected` en el heartbeat | critical | Al desaparecer |
| `clock_skew` | \|desfase\| mayor a 5 min | warning | Al corregirse |
| `error_rate_spike` | Tasa de error diaria del cliente mayor a `threshold` (default 15%) con al menos 20 turnos | warning | Al día siguiente bajo el umbral |
| `cost_spike` | Costo diario mayor a 3× la mediana de los 14 días previos, con mínimo de USD 5 | warning | Manual |
| `instance_warning` | El heartbeat trae `cert_expired`, `no_llm_provider` o `local_session_in_server` | critical | Al desaparecer |
| `instance_outdated` | Versión menor a `latest_version` por más de 30 días | info | Al actualizar |
| `no_usage` | Cliente activo con instancias online y cero turnos en 14 días | info | Al haber uso |

### 5.2 Motor

- Job cada 5 minutos: evalúa las reglas activas y hace
  `upsert` en `alerts` por `(rule_code, client_id, instance_id)` abierta.
  **Nunca** crea una segunda alerta abierta idéntica.
- Estados: `open` → `acknowledged` (con actor) → `resolved` (automática o
  manual, con nota).
- Tabla `alerts`: `id`, `rule_code`, `severity`, `client_id`,
  `instance_id` NULL, `status`, `details` JSONB, `opened_at`,
  `acknowledged_at/by`, `resolved_at/by`, `resolution_note`.
- **Notificaciones fuera de la consola** (email, chat) quedan fuera de
  alcance de esta fase. El motor expone un puerto `AlertNotifier` con
  implementación no-op, listo para conectarla.

## 6. Auditoría

- Tabla `audit_log` **solo inserción**: `id`, `occurred_at`,
  `actor_staff_id`, `actor_email`, `action` (p. ej.
  `instance.revoke`), `target_type`, `target_id`, `before` JSONB,
  `after` JSONB, `ip`, `user_agent`.
- Se escribe **en la misma transacción** que la acción. Si falla la
  auditoría, falla la acción.
- Se audita: login y fallos, cambios de MFA, toda escritura de §3,
  cambios de reglas y (Fase 5) recargas y ajustes de crédito.
- Nunca se guardan tokens ni secretos en `before`/`after`. Un
  serializador con lista de exclusión lo garantiza, con test.
- El usuario de BD de la aplicación no tiene `UPDATE` ni `DELETE` sobre
  `audit_log` (se aplica por migración con `REVOKE`).

## 7. Frontend `cloud/frontend`

### 7.1 Stack y arquitectura

Mismo stack que `frontend/` (Vue 3, Pinia, Vite, Vitest, Biome,
`vue-tsc`, Playwright), con `enterprise-frontend-architecture`. Módulos:

```
cloud/frontend/src/modules/
├── auth/        # login, MFA, setup de MFA
├── overview/
├── clients/
├── instances/
├── alerts/
├── enrollment/
├── staff/
└── audit/
```

Gráficas con `echarts`/`vue-echarts`, igual que la vista de consumo de
SAVI, para reutilizar patrones. Tokens de diseño copiados de SAVI para
mantener la identidad visual; **no** se comparten componentes en runtime
entre las dos aplicaciones.

### 7.2 Pantallas

| Ruta | Contenido |
|---|---|
| `/login`, `/mfa`, `/mfa/setup` | Flujo de §2.2. |
| `/` Resumen | Tarjetas (clientes, instancias online/offline, usuarios activos, turnos, costo), tendencia diaria, mezcla de proveedores, distribución de versiones y alertas abiertas. |
| `/clientes` | Tabla §3.2 con búsqueda, filtros y orden. Botón "Nuevo cliente". |
| `/clientes/:id` | Encabezado (estado, frescura, acciones). Pestañas: **Uso** (serie y desgloses §4.2), **Sucursales** (snapshot), **Usuarios** (ranking seudónimo), **Instancias**, **Vinculación** (tokens), **Alertas**. En la Fase 5 se suma **Créditos**. |
| `/instancias` | Tabla con conectividad, versión, cliente y última vez visto. Filtro "desactualizadas". |
| `/instancias/:id` | Datos, último heartbeat legible, estado por stream, avisos, historial de heartbeats y acciones (§3.3) con confirmaciones. |
| `/alertas` | Bandeja con filtros; reconocer y resolver con nota. |
| `/staff`, `/auditoria`, `/configuracion/alertas` | Administración. |

### 7.3 Detalles de interacción

- **Generar token:** diálogo que muestra el token **una vez**, con botón
  copiar e instrucción "Pegalo en SAVI → Administración → SAVI Cloud, o
  en el instalador". Al cerrar, no se puede volver a ver.
- **Revocar instancia:** hay que escribir `REVOCAR` y se explica que la
  instancia deja de enviar métricas y tendrá que vincularse con un token
  nuevo.
- **Frescura:** chip "datos hasta hace 3 min" en cada vista de cliente;
  ámbar después de 1 h y rojo después de 24 h.
- Cada métrica tiene un ícono de ayuda con la definición de §4.1.
- Responsive hasta 400 px; tablas con scroll horizontal propio.

## 8. Tests

### 8.1 Backend

| Test | Verifica |
|---|---|
| Matriz de permisos | **Test parametrizado que recorre todas las rutas** de `/console/api` y verifica el status por rol (`200`/`201` vs `403`). Falla si aparece una ruta sin `RequirePermission`. |
| Login | Mismo mensaje y piso de duración para email inexistente y contraseña mala; bloqueo tras 5 fallos. |
| MFA | Sin TOTP no hay tokens; código reutilizado rechazado; ventana ±1. |
| Refresh | Cookie `HttpOnly; Secure; SameSite=Strict`; revocado → `401`. |
| Tokens | El token solo aparece en la respuesta de creación; el listado nunca lo incluye. |
| Suspender cliente | Suspende sus instancias; el heartbeat siguiente devuelve `suspended`. |
| Métricas | Cada definición de §4.1 con un dataset pequeño y valores esperados escritos a mano (incluye superseded, costo nulo y zona horaria en el borde de medianoche). |
| Alertas | Cada regla abre y resuelve según su condición; no duplica alertas abiertas. |
| Auditoría | Toda escritura genera fila en la misma transacción; sin secretos; la app no puede `UPDATE`/`DELETE`. |
| Admin mínimo | No se puede desactivar el último admin. |

### 8.2 Frontend

- Vitest: guards por rol; diálogo de token de una sola vez; formateo de
  frescura; tooltips de definiciones.
- Playwright:
  1. Admin entra con TOTP (secreto de prueba conocido).
  2. Crea un cliente y genera un token.
  3. Una instancia de SAVI de prueba se vincula con ese token.
  4. La instancia aparece online en `/instancias` y sus métricas en el
     cliente.
  5. Un usuario `comercial` no ve el botón de revocar y el API le
     devuelve `403`.

### 8.3 Carga

Dataset sintético: 500 clientes, 1 instancia cada uno, 13 meses, 50.000
turnos/día. Verificar `overview` p95 < 1,5 s y `clients/{id}/metrics`
p95 < 800 ms. Verificar ingesta sostenida de 50 lotes/min sin degradar
la consola.
