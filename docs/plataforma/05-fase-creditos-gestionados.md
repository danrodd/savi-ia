# Fase 5 — IA gestionada por SEO: gateway y créditos

> Parte de: [PRD — Plataforma SAVI](00-prd.md)
> Estado: **propuesta**. Requiere resolver **P5** (unidad y precio del
> crédito) y **P8** (contrato y tratamiento de datos) antes de activarla
> con clientes reales.
> Depende de: [Fase 2](02-fase-vinculacion-y-sincronizacion.md) y
> [Fase 3](03-fase-consola-cloud.md).
> Alcance: `cloud/gateway` (deployable nuevo), `cloud/backend`
> (cuentas, ledger, precios, estados de cuenta), `cloud/frontend`
> (pestaña Créditos), y en SAVI los módulos `llm_providers` y
> `cloud_link` y la pantalla de proveedores.

## Resultado esperado

- [ ] **Spike 5.0** cerrado: los tres SDK funcionan contra un gateway por URL base, con informe.
- [ ] `cloud/gateway`: proxy nativo por proveedor, autenticación por instancia, lista blanca de rutas y modelos, medición y cobro.
- [ ] Lista de precios versionada por modelo (costo de SEO y precio de venta).
- [ ] Cuenta de créditos por cliente, ledger de solo inserción, recargas, ajustes y límite mensual.
- [ ] Modo de IA por instancia, asignado desde la consola y entregado por heartbeat.
- [ ] En SAVI: credencial `seo_managed`, resolución automática del proveedor, bloqueo previo al SSE sin créditos.
- [ ] Alertas de saldo bajo, agotado y límite mensual, en consola y en la administración de SAVI.
- [ ] Estado de cuenta mensual por cliente (JSON y CSV).
- [ ] Reconciliación diaria: saldo = ledger; costo del gateway ≈ costo reportado por las instancias (±1%).

---

## 1. Decisiones

| # | Decisión | Por qué |
|---|---|---|
| G1 | **Gateway como proxy nativo por proveedor**, no como traductor de formatos | El CLI de Claude habla la API de Messages; Gemini, `generateContent`; OpenAI, Responses. Reenviar el protocolo nativo no toca los runners, que ya están probados. Solo la **medición** necesita entender cada protocolo. |
| G2 | **Deployable separado** (`cloud/gateway`) | Es el camino caliente: latencia, escalado y disponibilidad distintos de la consola y la ingesta. Un despliegue de la consola no puede cortar el chat de los clientes gestionados. |
| G3 | **Autenticación con el mismo secreto de instancia** de la Fase 2 | Una sola credencial que rotar y revocar. Revocar una instancia corta también su IA. |
| G4 | **Cobro por request al terminar**, con sobregiro acotado | El costo de un stream se conoce al final. Reservar el máximo teórico bloquearía saldos chicos sin razón. |
| G5 | **Montos en micro-USD enteros** (`BIGINT`) | Sin errores de punto flotante. La presentación en "créditos" o COP es solo formato (P5). |
| G6 | **Ledger de solo inserción** + saldo materializado en la cuenta | Auditable y reconstruible. El saldo en la fila permite validar en O(1) antes de cada request. |
| G7 | **Sin precio, no hay servicio** | Un modelo sin precio vigente se rechaza. Servir consumo que no se puede cobrar es pérdida silenciosa. |
| G8 | **Nunca se guardan cuerpos** de request ni de response | Los prompts llevan datos del ERP ya interpretados (R8 del PRD). |

## 2. Spike 5.0: verificación previa (obligatorio)

Antes de escribir el gateway, un prototipo mínimo con un proxy de
reenvío (FastAPI + `httpx`, en streaming, sin cobro) confirma:

| # | Verificación | Cómo |
|---|---|---|
| V1 | El CLI de Claude, lanzado por `claude-agent-sdk`, funciona con `ANTHROPIC_BASE_URL` apuntando al proxy y `ANTHROPIC_AUTH_TOKEN` con el secreto de instancia, pasados por `ClaudeAgentOptions(env=…)` como ya se pasa la credencial por turno | Turno real con las 4 tools, título y `edit_last` |
| V2 | Qué rutas llama el CLI además de `/v1/messages` (conteo de tokens, listado de modelos, telemetría) | Log de rutas del proxy. De ahí sale la lista blanca. Si hay tráfico no esencial, probar `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` |
| V3 | `google-genai` funciona con `HttpOptions(base_url=…)` y la clave de instancia en lugar de la API key | Turno real con function calling y *thought signatures* |
| V4 | `openai` funciona con `base_url` y `api_key` de instancia en la Responses API con `store=False` y reasoning items | Turno real con tools y segundo request |
| V5 | Dónde aparece el `usage` final en cada stream | Anthropic: `message_start` + `message_delta`. Gemini: `usageMetadata` del último chunk. OpenAI: `response.completed`. Confirmar con capturas reales. |
| V6 | Sobrecosto de latencia del proxy hasta el primer token | p95 sobre 50 requests, objetivo < 150 ms (RNF-09) |

**Informe:** `docs/plataforma/spike-gateway.md`, con la lista blanca de
rutas, capturas de `usage` y medidas. Si V1 falla, la alternativa a
evaluar es que el modo gestionado para Claude use la API directa en un
runner nuevo. Eso contradice `CLAUDE.md` §10 y requiere decisión
explícita del usuario.

Alternativa a comparar en el mismo spike: un proxy de terceros con
presupuestos por clave virtual. Criterios: soporte de *pass-through*
nativo de los tres protocolos, medición exacta en streaming, no guardar
cuerpos, e integración con **nuestro** ledger. Si no cumple los cuatro,
se implementa el proxy propio descrito abajo.

## 3. Gateway (`cloud/gateway`)

### 3.1 Rutas

| Prefijo entrante | Destino | Credencial inyectada |
|---|---|---|
| `/anthropic/*` | `https://api.anthropic.com/*` | `x-api-key: <clave SEO>` |
| `/gemini/*` | `https://generativelanguage.googleapis.com/*` | `x-goog-api-key: <clave SEO>` |
| `/openai/*` | `https://api.openai.com/*` | `Authorization: Bearer <clave SEO>` |

- Solo rutas de la **lista blanca** que produce el spike (V2). El resto →
  `404 route_not_allowed`.
- Se **eliminan** los headers de credencial del cliente antes de
  reenviar. Nunca llega al proveedor el secreto de la instancia.
- Claves de SEO en un gestor de secretos del proveedor de nube (P3), con
  rotación sin reinicio.

### 3.2 Pipeline por request

```
1. Autenticar instancia: hash del bearer/api-key → instances (cache 60 s, invalidación por evento)
2. Instancia active, cliente active, ai_mode = managed           → 403 managed_ai_disabled
3. Modelo del body ∈ modelos permitidos del cliente               → 403 model_not_allowed
4. Precio vigente para (provider, model)                          → 403 model_not_priced
5. Cuenta: estado y límites (§4.3)                                → 402 credits_exhausted | monthly_limit_reached
6. Rate limit por instancia (tokens/min y requests/min)           → 429 + Retry-After
7. Reenviar en streaming (sin buffer), con tee hacia el medidor
8. Al terminar (éxito, error del proveedor o corte del cliente):
     usage medido → costo con precio de venta → cobro atómico (§4.4) → gateway_requests
```

- Timeouts: conexión 10 s, stream hasta 10 min, igual que el tope de un
  turno largo de SAVI.
- **Corte del cliente a mitad de stream:** se cobra lo que el proveedor
  reporte. Si no llega `usage` final, se cobra la estimación (§3.3).
- Errores del proveedor (`4xx`/`5xx`) se devuelven tal cual al runner,
  que ya los maneja, y no se cobran si el proveedor no reporta `usage`.

### 3.3 Medición

`app/metering/{anthropic,gemini,openai}.py`: parsers incrementales del
stream que extraen `input_tokens`, `output_tokens`,
`cache_read_input_tokens` y `cache_creation_input_tokens` (los mismos
nombres que `messages.usage` de SAVI).

- Si el stream termina sin `usage` (corte), se estima con los caracteres
  emitidos ÷ 4 para salida y el tamaño del body ÷ 4 para entrada, con
  `usage_estimated = true`. El estado de cuenta lo marca.
- Test por proveedor con **capturas reales** del spike como fixtures.

### 3.4 `gateway_requests` (Postgres Cloud, particionada por mes, 13 meses)

`id`, `client_id`, `instance_id`, `provider`, `model`, `route`,
`status_code`, `started_at`, `first_byte_ms`, `duration_ms`, 4
contadores de tokens, `usage_estimated`, `cost_micro_usd` (costo de
SEO), `price_micro_usd` (venta), `price_version_id`, `ledger_hour`
(para el rollup). **Sin cuerpos, sin prompts, sin headers.**

## 4. Créditos

### 4.1 Precios: `model_prices`

| Columna | Notas |
|---|---|
| `id` | |
| `provider`, `model` | |
| `cost_input`, `cost_output`, `cost_cache_read`, `cost_cache_write` | micro-USD por **millón** de tokens. Lista de precios del proveedor. |
| `sale_input`, `sale_output`, `sale_cache_read`, `sale_cache_write` | micro-USD por millón. Lo que paga el cliente. |
| `effective_from` | Un precio nuevo es una fila nueva; nunca se edita una vigente. |
| `created_by`, `created_at` | Auditado. |

La consola calcula y muestra el margen. Cada request guarda el
`price_version_id` con el que se cobró.

### 4.2 `credit_accounts` y `credit_ledger`

**`credit_accounts`** (una por cliente): `client_id` PK,
`balance_micro_usd BIGINT`, `overdraft_limit_micro_usd` (default 1 USD),
`monthly_limit_micro_usd` NULL, `hard_stop BOOL` (default `true`),
`low_balance_threshold_micro_usd`, `status` (`active`/`frozen`),
`version` (lock optimista), `updated_at`.

**`credit_ledger`** (solo inserción, `REVOKE UPDATE, DELETE`):

| Columna | Notas |
|---|---|
| `id`, `client_id` | |
| `kind` | `topup` \| `usage` \| `adjustment` \| `refund` \| `expiry` |
| `amount_micro_usd` | Con signo: `topup` positivo, `usage` negativo. |
| `balance_after_micro_usd` | Saldo después del movimiento. |
| `reference` JSONB | `topup`: número de factura del ERP de SEO y medio de pago. `usage`: `{hour, requests, tokens, by_model}`. `adjustment`: motivo. |
| `created_by_staff_id` | NULL para `usage`. |
| `created_at` | |

### 4.3 Reglas de autorización (paso 5 del pipeline)

```
si account.status = frozen                                  → 402 credits_exhausted
si hard_stop y balance <= -overdraft_limit                  → 402 credits_exhausted
si monthly_limit y consumo_mes_actual >= monthly_limit      → 402 monthly_limit_reached
```

- `consumo_mes_actual` sale de un contador materializado por
  `(client_id, mes)`, actualizado en el mismo cobro. No se suman
  requests en cada llamada.
- Con `hard_stop = false` (clientes de confianza, pospago), el saldo
  puede quedar negativo sin límite y solo se alerta.
- Mes calendario en `America/Bogota`.

### 4.4 Cobro atómico

Al terminar cada request, en **una** transacción:

```sql
UPDATE credit_accounts
   SET balance_micro_usd = balance_micro_usd - :price, version = version + 1
 WHERE client_id = :client
RETURNING balance_micro_usd;
-- + UPSERT del contador mensual + INSERT en gateway_requests
```

- **Rollup horario:** un job inserta un `credit_ledger` `usage` por
  `(client_id, hora)` con la suma de `gateway_requests` de esa hora, y
  marca `ledger_hour`. El saldo ya se descontó en tiempo real; el ledger
  lo documenta. Así el ledger no crece a una fila por request.
- **Invariante de reconciliación (job diario):**
  `balance = Σ ledger + Σ(price de gateway_requests aún sin rollup)`.
  Si no se cumple → alerta `ledger_mismatch` (critical) y
  `account.status = frozen` hasta revisión manual.

### 4.5 Operaciones del staff (consola)

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/console/api/clients/{id}/credits` | `credits.read`: saldo, límite, consumo del mes, proyección a fin de mes, últimos movimientos |
| `POST` | `/console/api/clients/{id}/credits/topups` | `credits.topup`: `{amount_micro_usd, invoice_number, note}` |
| `POST` | `/console/api/clients/{id}/credits/adjustments` | `credits.adjust` (solo `admin`): `{amount_micro_usd, reason}` |
| `PATCH` | `/console/api/clients/{id}/credits/settings` | `credits.configure`: límite mensual, `hard_stop`, umbral, sobregiro |
| `GET/POST` | `/console/api/model-prices` | `prices.manage` (solo `admin`) |
| `PATCH` | `/console/api/clients/{id}/ai` | `ai.configure`: `{mode: own_key \| managed, allowed: {claude: [modelos], …}, default_provider, default_chat_model, default_title_model}` |
| `GET` | `/console/api/clients/{id}/statements/{yyyy-mm}` | `credits.read`: `?format=json\|csv` (§6) |

Permisos nuevos en la matriz de la Fase 3: `comercial` tiene
`credits.read`, `credits.topup` y `ai.configure`; `admin` tiene todos.
**Toda** operación se audita (Fase 3 §6).

## 5. Integración en SAVI

### 5.1 Heartbeat: campo `ai`

La respuesta del heartbeat (Fase 2 §3.2) completa `ai`:

```json
"ai": {
  "mode": "managed",
  "gateway_url": "https://gw.<dominio-seo>",
  "default_provider": "claude",
  "default_chat_model": "claude-sonnet-4-6",
  "default_title_model": "claude-haiku-4-5",
  "allowed": { "claude": ["claude-sonnet-4-6", "claude-haiku-4-5"] },
  "sale_prices": { "claude-sonnet-4-6": { "input": 3.6, "output": 18.0, "cache_read": 0.36, "cache_write": 4.5 } },
  "credits": { "status": "ok", "balance_display": "USD 42,10", "month_usage_display": "USD 17,90", "month_limit_display": "USD 60,00" }
}
```

`credits.status`: `ok` \| `low` \| `exhausted` \| `limit_reached`.
`sale_prices` está en USD por millón, como la tabla de precios que ya usa
`llm_providers`. `null` o `mode: own_key` = sin modo gestionado.

### 5.2 `llm_providers`: credencial `seo_managed`

- Nuevo `credential_kind = "seo_managed"`. **No se puede elegir** desde la
  UI ni desde `PATCH /admin/llm-providers`: lo escribe solo `cloud_link`
  al procesar el heartbeat.
- Al recibir `mode: managed`:
  1. Upsert de la configuración del proveedor por defecto con
     `credential_kind = seo_managed`, modelos por defecto y `pricing =
     sale_prices`, para que `cost_usd` local refleje lo que paga el
     cliente.
  2. Activarlo e invalidar la caché de `ActiveProviderResolver` (patrón
     de generación existente).
  3. Guardar la configuración de clave propia previa **sin borrarla**
     (`previous_config`) para restaurarla si SEO vuelve a `own_key`.
- Al recibir `mode: own_key` estando en `managed`: restaurar
  `previous_config`. Si no existe, queda sin proveedor
  (`no_llm_provider`) y el administrador lo configura.
- Resolución de credencial por runner con `seo_managed`:

| Runner | Configuración |
|---|---|
| Claude | `env = {ANTHROPIC_BASE_URL: f"{gateway_url}/anthropic", ANTHROPIC_AUTH_TOKEN: <secreto>}` (+ variables que defina V2) |
| Gemini | `HttpOptions(base_url=f"{gateway_url}/gemini")`, `api_key = <secreto>` |
| OpenAI | `base_url = f"{gateway_url}/openai/v1"`, `api_key = <secreto>` |

  El secreto se lee de `cloud_link` en cada turno, así una rotación
  (Fase 2 §3.4) aplica sin reiniciar. **Nunca** se escribe en
  `llm_provider_configs`.

### 5.3 Bloqueo antes del SSE

`ActiveProviderResolver.resolve()` (ya se llama antes del
`StreamingResponse` en `chat/infrastructure/http/routes.py`) suma:

| Condición | Resultado |
|---|---|
| `seo_managed` y `credits.status ∈ {exhausted, limit_reached}` | `409 llm_provider_unavailable` con `reason: credits_exhausted` o `monthly_limit_reached` |
| `seo_managed` y la instancia no está `linked` (revocada, sin secreto) | `409 llm_provider_unavailable` con `reason: managed_ai_unavailable` |

- El estado de créditos es el del último heartbeat (hasta 5 minutos de
  desfase). El gateway es la autoridad: si el saldo se agota a mitad de
  sesión, responde `402` y el runner emite el `ErrorEvent` legible
  (§5.4).
- **Sin conexión a Cloud en modo gestionado no hay IA.** Es una
  consecuencia aceptada del modo (§5 del PRD) y se explica en la UI.

### 5.4 Mensajes al usuario

| `reason` / error | Usuario del chat | Administrador |
|---|---|---|
| `credits_exhausted` | "El servicio de IA de tu empresa no tiene saldo disponible. Avisale a tu administrador." | Banner: "Sin créditos de IA. Contactá a SEO Group para recargar." |
| `monthly_limit_reached` | "Tu empresa alcanzó el límite mensual de uso de IA." | Banner con límite y fecha de reinicio |
| `managed_ai_unavailable` | "El servicio de IA no está disponible en este momento." | Banner con el estado de la vinculación |
| `402` del gateway a mitad de turno | Mismo texto que `credits_exhausted`, como `ErrorEvent` | — |

Nunca se muestran nombres de proveedor, gateway ni infraestructura al
usuario final (regla de confidencialidad de SAVI).

### 5.5 Frontend de SAVI: Proveedores de IA

- En modo gestionado, `LlmProvidersView` reemplaza las tarjetas
  editables por una tarjeta **"IA gestionada por SEO Group"**, con modelos
  en uso, saldo, consumo del mes, límite y estado. Sin botones de
  configuración.
- La vista de consumo sigue funcionando: `cost_usd` se calcula con los
  precios de venta (§5.2).
- Banner global de administración según §5.4, con prioridad sobre los
  avisos de la Fase 1.

## 6. Estado de cuenta mensual

`GET /console/api/clients/{id}/statements/{yyyy-mm}`:

```json
{
  "client": { "code": "FARMX", "name": "Farmacias X", "nit": "…" },
  "period": "2026-09",
  "opening_balance_micro_usd": 50000000,
  "topups": [ { "date": "2026-09-02", "amount_micro_usd": 20000000, "invoice_number": "FE-1234" } ],
  "adjustments": [],
  "usage": {
    "total_micro_usd": 27900000,
    "by_model": [ { "provider": "claude", "model": "claude-sonnet-4-6", "requests": 8123, "input_tokens": 0, "output_tokens": 0, "amount_micro_usd": 25100000 } ],
    "by_day": [ { "day": "2026-09-01", "amount_micro_usd": 910000 } ],
    "estimated_requests": 12
  },
  "closing_balance_micro_usd": 42100000
}
```

- `opening + topups + adjustments − usage = closing`, verificado al
  generar. Si no cierra → `500` y alerta `ledger_mismatch`; nunca se emite
  un estado de cuenta inconsistente.
- CSV con las mismas secciones, en UTF-8 con BOM (Excel en Windows).
- El estado de cuenta **no es una factura**: la factura electrónica la
  emite SEO en su ERP con estos totales (fuera de alcance, PRD §3).

## 7. Alertas nuevas (motor de la Fase 3)

| `code` | Condición | Severidad |
|---|---|---|
| `credits_low` | Saldo menor al umbral, o consumo del mes ≥ 80% del límite | warning |
| `credits_exhausted` | Rechazos `402 credits_exhausted` en la última hora | critical |
| `monthly_limit_reached` | Rechazos `402 monthly_limit_reached` | warning |
| `ledger_mismatch` | Falla la invariante de §4.4 | critical |
| `gateway_error_rate` | Más del 5% de `5xx` del proveedor en 15 minutos | critical |
| `margin_negative` | Un precio de venta vigente menor al costo | critical |

## 8. Operación del gateway

- Mínimo 2 réplicas detrás del balanceador, en la región más cercana a
  los proveedores con buena latencia hacia Colombia (P3).
- `GET /health` sin dependencias; `GET /ready` con BD y caché.
- Métricas: requests por estado, `first_byte_ms` p50/p95, duración y
  errores por proveedor. Sin etiquetas de alta cardinalidad (nada de
  `instance_id` en métricas; eso va a `gateway_requests`).
- Logs: `request_id`, `instance_id`, `provider`, `model`, `status` y
  duraciones. **Nunca** cuerpos, headers de autorización ni query
  strings con claves (test con un logger capturado).
- SLO propuesto: 99,5% mensual de disponibilidad del gateway (R9).

## 9. Tests

### 9.1 Gateway

| Test | Verifica |
|---|---|
| Autenticación | Secreto válido, anterior en período de gracia, revocado, instancia suspendida, cliente en `own_key`. |
| Lista blanca | Ruta fuera de la lista → `404`; los headers de credencial del cliente no llegan al upstream (upstream fake que registra headers). |
| Modelo | No permitido → `403`; sin precio → `403`. |
| Autorización de saldo | Cada rama de §4.3, incluidos sobregiro y `hard_stop = false`. |
| Streaming | Los bytes llegan al cliente sin buffer (primer chunk antes de que el upstream termine). |
| Medición | Fixtures reales de los tres proveedores → tokens exactos; corte a mitad → estimación marcada. |
| Cobro concurrente | 200 requests simultáneos del mismo cliente → saldo final exacto, sin carreras. |
| Sin cuerpos en logs | Ningún fragmento del prompt de prueba aparece en logs ni en `gateway_requests`. |

### 9.2 Cloud backend

- Ledger: solo inserción (la app no puede `UPDATE`/`DELETE`); rollup
  horario idempotente; invariante diaria y congelamiento ante
  inconsistencia.
- Precios: una fila nueva no altera el cobro de requests anteriores.
- Estado de cuenta: ecuación de cierre con dataset conocido; CSV con BOM.
- Permisos nuevos en el test parametrizado de la Fase 3.

### 9.3 SAVI

| Test | Verifica |
|---|---|
| Heartbeat `managed` | Crea y activa `seo_managed`, guarda `previous_config`, invalida la caché del resolver. |
| Vuelta a `own_key` | Restaura la configuración previa. |
| API admin | `seo_managed` no se puede crear ni editar por API (`422`). |
| Resolución por runner | Claude recibe `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`; Gemini, `base_url` y clave; OpenAI, `base_url` y clave; el secreto nunca se persiste en `llm_provider_configs`. |
| Bloqueo previo | `exhausted` y `limit_reached` → `409` con `reason` antes del SSE. |
| `402` a mitad de turno | `ErrorEvent` con el mensaje de §5.4, sin nombres de infraestructura. |
| Costo local | `cost_usd` con `sale_prices`. |

### 9.4 E2E y reconciliación (criterio de cierre)

1. Cliente de prueba con USD 1 de saldo, `hard_stop = true` y modo
   gestionado con Claude.
2. Instancia de prueba vinculada: el heartbeat activa `seo_managed`.
3. Turnos reales hasta agotar el saldo: el siguiente turno devuelve
   `409 credits_exhausted` antes del SSE y la administración de SAVI
   muestra el banner.
4. Recarga desde la consola: al siguiente heartbeat el chat vuelve a
   funcionar.
5. **Verificar:** saldo de la cuenta = Σ ledger; Σ `price_micro_usd` del
   gateway ≈ Σ `cost_usd` de `ev_turns` de la instancia (±1%); el estado
   de cuenta cierra.
