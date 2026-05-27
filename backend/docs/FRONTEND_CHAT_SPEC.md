# Spec del API del chat — handoff backend → frontend

> Documento para el desarrollador frontend. Cuenta cómo arrancar el
> backend, qué endpoints existen y cómo consumir el stream del chat.
> Pensado para una UI tipo ChatGPT: sidebar con lista de conversaciones
> + área de mensajes + input.

---

## 0. Base URL y CORS

- **Dev local**: `http://127.0.0.1:8000` (o el puerto que arranques).
- **CORS**: el backend permite los orígenes en `CORS_ALLOWED_ORIGINS`
  (`.env`). El frontend Vite suele ser `http://localhost:5173`; ya
  está en el default. Si usas otro puerto, agrégalo.

---

## 1. Modelos

### Conversation
```ts
type Conversation = {
  id: string;            // UUID
  user_id: string | null; // por ahora siempre null (auth pendiente)
  title: string;
  title_locked: boolean; // true tras un PATCH manual del usuario
  created_at: string;    // ISO 8601 UTC
  updated_at: string;
}
```

### Message
```ts
type Message = {
  id: string;             // UUID
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
  // Metadata del turno (sólo presente en mensajes role=assistant)
  finish_reason: "complete" | "interrupted" | "error" | "truncated" | null;
  tool_invocations: ToolInvocation[]; // [] si no hubo tools
  usage: TokenUsage | null;
  cost_usd: string | null; // Decimal serializado como string
  // Revisiones: si superseded_at != null, este mensaje ya no es parte
  // del hilo activo. superseded_by_id apunta al que lo reemplazó.
  superseded_at: string | null;       // ISO 8601 UTC
  superseded_by_id: string | null;    // UUID
}

type ToolInvocation = {
  id: string;            // toolu_xxx
  name: string;          // mcp__savi__info_empresa, etc.
  input: Record<string, unknown>;
  status: "running" | "ok" | "error";
}

type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
}
```

> **Para la UI**: Usa `tool_invocations` para rehidratar los chips de
> tools en mensajes históricos (cuando el usuario recarga una
> conversación). `finish_reason === "interrupted"` indica respuesta
> cortada — muéstralo como nota visual. `usage` y `cost_usd` son útiles
> para un panel admin/observabilidad; no los muestres al usuario final.

---

## 2. Endpoints REST

### `POST /conversations` — crear conversación

**Body** (`Content-Type: application/json`):
```json
{ "title": "Nueva conversación", "user_id": null }
```
Ambos campos son opcionales. Si omites `title`, se usa
`"Nueva conversación"`. `user_id` queda `null` hasta que haya auth.

**Respuesta `201`**:
```json
{
  "id": "856d84c7-...",
  "user_id": null,
  "title": "Nueva conversación",
  "created_at": "2026-05-27T00:41:13.971Z",
  "updated_at": "2026-05-27T00:41:13.971Z"
}
```

---

### `GET /conversations` — listar conversaciones

**Query params** (todos opcionales):
- `user_id`: UUID para filtrar.
- `limit`: 1–200 (default 50).
- `offset`: ≥0 (default 0).

**Respuesta `200`**: `Conversation[]` ordenadas por `updated_at` desc.

> **Para el sidebar**: hoy no hay auth, así que llama
> `GET /conversations` sin `user_id` y muestra todo. Cuando entre auth
> se filtrará automáticamente desde el backend.

---

### `DELETE /conversations/{id}` — soft delete idempotente

**Respuesta `204 No Content`** si la conversación existía (esté ya
eliminada o no). **`404`** si nunca existió.

Tras el DELETE, la conversación deja de aparecer en `GET /conversations`
y `GET /conversations/{id}` devuelve `404`. Los mensajes quedan en BD
(soft delete real) pero invisibles al usuario.

**Idempotente**: dos `DELETE` seguidos sobre la misma conversación
devuelven `204` ambos. Útil cuando el cliente reintenta por timeout
o cuando el usuario hace doble click.

**No interrumpe turnos en curso**: si el cliente tiene un `POST /chat`
streameando cuando llega el `DELETE`, el stream sigue hasta su `done`
y la respuesta del asistente se persiste igual (queda en una
conversación invisible — coherente con soft delete). En la UI, ocultá
la conversación del sidebar apenas mandes el `DELETE` sin esperar al
stream.

> Frontend: deshabilita el botón "Eliminar" mientras hay un POST /chat
> activo, **o** acepta que el stream termine en background y muestra
> al usuario que la conversación se eliminó. Lo recomendado: ocultar
> del sidebar inmediatamente (optimistic update) y al recibir el 204
> confirmar; revertir si 4xx.

---

### `PATCH /conversations/{id}` — renombrar manualmente

**Body**:
```json
{ "title": "Mi título personalizado" }
```

`title` requerido, 1–200 chars.

**Respuesta `200`**: la `Conversation` actualizada con `title_locked: true`.
A partir de este momento ningún autotítulo del backend la sobrescribirá.

Úsalo desde el botón "Renombrar" del sidebar.

---

### `GET /conversations/{id}` — conversación + mensajes

**Query params**:
- `include_superseded: bool` (default `false`) — si true, devuelve también
  las versiones anteriores de mensajes editados o regenerados (con
  `superseded_at`/`superseded_by_id` set).

**Respuesta `200`**:
```json
{
  "conversation": { ... Conversation },
  "messages": [ ... Message[] ordenados por created_at asc ]
}
```

Úsalo al abrir una conversación en el panel central para hidratar el
historial. Con `?include_superseded=true` lo usas para el panel de
"ver versiones anteriores" de un mensaje editado/regenerado.

---

### `POST /chat` — enviar / editar / regenerar (todos stream)

**Body** discriminado por `action`:

```ts
type ChatBody =
  | { conversation_id: string; action?: "send"; message: string }
  | { conversation_id: string; action: "edit_last"; message: string }
  | { conversation_id: string; action: "regenerate" }
```

- `action: "send"` (default si se omite) — envío normal del primer
  mensaje o de uno nuevo. Requiere `message` (1–16000 chars).
- `action: "edit_last"` — reemplaza el último mensaje del usuario
  activo. Marca el viejo (y el assistant que le respondió, si existe)
  como `superseded` y regenera la respuesta. Requiere `message`.
- `action: "regenerate"` — regenera la última respuesta del asistente
  sin tocar el mensaje del usuario. NO requiere `message`.

**Errores antes del stream** (status 422 con `detail`):
- `edit_last` sin nada que editar: "No hay un mensaje del usuario que
  se pueda editar en esta conversación".
- `regenerate` sin respuesta del asistente: "No hay una respuesta del
  asistente que se pueda regenerar; envía primero un mensaje".

Estos errores llegan **antes** del SSE, así que llegan como JSON normal.
Cuando uses `edit_last` o `regenerate`, deshabilita el botón si no se
cumplen las precondiciones (el frontend ya sabe quién es el último
mensaje activo) en lugar de esperar al 422.

**Respuesta**: `Content-Type: text/event-stream` con eventos SSE
estándar separados por `\n\n`, cada uno con prefijo `data: `.

#### Tipos de eventos

Todos los payloads incluyen `type`. Otros campos varían:

| `type`            | Otros campos                                       | Para qué |
|-------------------|----------------------------------------------------|----------|
| `text_delta`      | `text: string`                                     | Append al markdown del asistente |
| `thinking_delta`  | `text: string`                                     | (Opcional) mostrar "pensando…" colapsable |
| `tool_use`        | `id: string`, `name: string`, `input: object`     | El agente está llamando una tool; muestra spinner |
| `tool_result`     | `tool_use_id: string`, `is_error: bool`           | Cierra el spinner de esa tool |
| `superseded`      | `message_ids: string[]`                            | Llega al inicio del stream en `edit_last` y `regenerate`. Lista de IDs que pasan a ser superseded: ocúltalos del hilo activo. |
| `title_update`    | `title: string`                                    | Renombra la conversación en el sidebar en vivo. Llega 0, 1 o 2 veces por turno (fase provisional + fase refinada). Sólo en conversaciones cuyo título sigue siendo el default. |
| `done`            | `usage: object \| null`, `cost_usd: number \| null`, `finish_reason: string` | Cierre limpio |
| `error`           | `message: string`                                  | El stream falló; muestra error y permite reintentar |

#### Ejemplo crudo del stream

```
data: {"type":"thinking_delta","text":"The user is greeting..."}

data: {"type":"text_delta","text":"¡Hola! Soy **SAVI**..."}

data: {"type":"text_delta","text":" el asistente del ERP de SEO Group."}

data: {"type":"done","usage":{...},"cost_usd":0.012,"finish_reason":"complete"}
```

---

## 3. Cómo consumir el stream en el frontend (TypeScript)

`EventSource` solo soporta GET, así que para `POST /chat` usa
`fetch` + `getReader()` + parser SSE manual:

```ts
async function sendChat(
  conversationId: string,
  message: string,
  onEvent: (evt: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE: eventos separados por \n\n
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        try {
          onEvent(JSON.parse(line.slice(6)) as ChatEvent);
        } catch {
          // payload corrupto — ignorar
        }
      }
    }
  }
}
```

Para el **botón "Detener"**, pasa un `AbortController`:
```ts
const ctrl = new AbortController();
sendChat(convId, text, handle, ctrl.signal);
// luego: ctrl.abort();
```

El backend hace persistencia "best-effort" del mensaje del asistente
al cerrar el stream, así que la respuesta parcial queda guardada.

---

## 4. Auto-título — comportamiento esperado en la UI

El backend genera el título automáticamente la primera vez que se chatea
en una conversación cuyo título sigue siendo `"Nueva conversación"`. El
flujo:

1. El usuario crea una conversación → llega `Conversation` con
   `title: "Nueva conversación"`, `title_locked: false`. **El sidebar
   muestra "Nueva conversación"**.
2. El usuario manda el primer mensaje. Por el SSE recibes 0–2 eventos
   `title_update`:
   - **Fase 1** (al ~1–2 s): título provisional con sólo el `user_msg`.
     Ej.: `"Información de la empresa"`. **Actualiza el sidebar al
     vuelo** sin pedir nada al backend.
   - **Fase 2** (al cierre del turno, si llega antes del timeout):
     título refinado con la respuesta del asistente a la vista. Ej.:
     `"NIT y razón social"`. **Actualiza el sidebar otra vez**.
3. Si el cliente cancela el primer turno antes del DONE: la **fase 1
   sigue corriendo en background** y el título se persiste igual. Si
   recargas la conversación con `GET /conversations/{id}` verás el
   título actualizado.
4. Si el usuario hace `PATCH /conversations/{id}` para renombrar a
   mano, la response trae `title_locked: true` y **ningún `title_update`
   futuro lo va a sobrescribir**. La UI debería mostrar un indicador
   sutil (icono de candado, opcional) de que el título está fijado.

> **No hagas polling** del título — confía en los eventos SSE
> + la response de `PATCH`. Si el usuario llega tarde a una
> conversación cancelada (caso del paso 3), el `GET` de hidratación
> al abrirla resuelve.

---

## 5. Editar último mensaje y regenerar — revisiones

El backend usa **soft branches**: editar o regenerar **nunca borra** un
mensaje. El viejo queda con `superseded_at` y `superseded_by_id`. Esto
te da trazabilidad sin árbol completo de versiones.

### Editar el último mensaje del usuario

Botón "Editar" visible solo en el **último** mensaje del usuario del
hilo activo. Al confirmar:

```ts
POST /chat
{ "conversation_id": "...", "action": "edit_last", "message": "texto nuevo" }
```

Llega un `superseded` con 1 o 2 ids (el user viejo + el assistant si
existía). Ocúltalos del hilo y pinta el nuevo mensaje del usuario +
empieza a renderizar la respuesta como en `send` normal.

### Regenerar la última respuesta del asistente

Botón "Regenerar" visible solo en el **último** mensaje del asistente
del hilo activo. Al hacer click:

```ts
POST /chat
{ "conversation_id": "...", "action": "regenerate" }
```

Llega un `superseded` con 1 id (el assistant viejo). Ocúltalo y empieza
a renderizar la nueva respuesta.

### Ver versiones anteriores

Para reconstruir las versiones de un mensaje editado/regenerado:

```
GET /conversations/{id}?include_superseded=true
```

Trae **todos** los mensajes en orden de `created_at`, incluidos los
superseded. Reconstrucción:
- Versiones del par (user2, asst2): seguir la cadena
  `superseded_by_id` hacia adelante desde `user2`. Cada salto te lleva
  a la siguiente versión activa o superseded.
- Si quieres mostrar `< 2 / 3 >` en el mensaje activo, cuenta cuántos
  superseded apuntan eventualmente hacia él (los previos) y permite
  navegar entre ellos (vista de solo lectura — no se puede "volver" a
  una versión vieja como acción, solo verla).

### UI sugerida

- En cada mensaje activo del usuario: si `superseded_by_id` está set
  en alguna versión anterior de ese turno, muestra `< 1 / N >` con
  flechas para navegar a las versiones anteriores en read-only.
- Igual para mensajes del asistente regenerados.

### Reglas duras del backend

- `edit_last` solo aplica al **último user activo**. No se puede editar
  un mensaje intermedio. Si el frontend trata, el backend devuelve
  422 con "No hay un mensaje del usuario que se pueda editar".
- `regenerate` solo aplica al **último assistant activo**. Si el último
  activo es un user (cancel sin respuesta), el backend devuelve 422
  con "No hay una respuesta del asistente que se pueda regenerar".

---

## 6. Comportamiento de SAVI a respetar en la UI

- SAVI **rechaza** cualquier pregunta fuera de SEO Group (en cualquier
  idioma, con cualquier formulación). NO programes en el frontend
  ningún workaround para "forzar" respuestas off-topic.
- SAVI **nunca debe mostrar SQL crudo ni nombres internos** de tablas/
  columnas al usuario funcional. Si en el stream llega un `text_delta`
  con SQL, **renderízalo igual** — eso es un bug del backend (avisa).
- Los `tool_use` y `tool_result` son útiles para mostrar feedback
  ("Consultando información de tu empresa…"), pero **no muestres el
  nombre técnico de la tool** (`mcp__savi__info_empresa`). Trádúcelo
  o muestra solo un spinner.

---

## 7. Stack sugerido para el frontend

Recomendaciones del equipo (no obligatorias):

- **Vue 3 + Composition API + `<script setup>`** — ya está iniciado.
- **Tailwind CSS** + plugin `@tailwindcss/typography` para renderizar
  el markdown de las respuestas (`prose prose-slate dark:prose-invert`).
- **`markdown-it`** para el render de markdown del asistente (es la
  propuesta del equipo y es buena: ligero, sin dependencias React,
  fácil de extender con plugins para tablas / fences / etc.).
- **Pinia** para el store de conversaciones.
- **Vue Router** con rutas tipo `/c/:conversationId`.

---

## 8. Layout objetivo (referencia visual)

```
┌────────────────────────────────────────────────────────────┐
│  [+] Nueva conversación                                    │
│  ───────────────────────────────────                       │
│ │ Conversaciones                       │  ¿Cuál es el NIT? │
│ │ ▸ Datos de mi empresa  (hace 2 min) │                   │
│ │ ▸ Saludo inicial       (hoy)        │  ¡Hola! …         │
│ │ ▸ ...                                │                   │
│ │                                      │  [Input message]  │
└─────────── sidebar ─────────────────── main chat ──────────┘
```

---

## 9. Cómo arrancar el backend (para probar el frontend en local)

Desde `SAVI_SEO-ERP/backend/`:

```powershell
$env:Path = "C:\Users\hikig\.local\bin;$env:Path"
cp .env.example .env  # rellena ANTHROPIC_API_KEY y passwords
uv sync
uv run alembic upgrade head
uv run python -m uvicorn app.main:app --reload --port 8000
```

Verificar:
```powershell
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"SAVI","env":"development"}
```

OpenAPI / Swagger UI en `http://127.0.0.1:8000/docs`.

---

## 10. Limitaciones conocidas del MVP

- **Sin auth**. El backend acepta cualquier request. No expongas el
  endpoint en internet hasta que entre auth.
- **Sin rate limit**. Una pestaña abierta puede gastar tokens rápido.
- **Edición sólo del último**. No se puede editar mensajes intermedios
  ni hacer bifurcaciones desde el medio del hilo (ChatGPT lo permite —
  nosotros no en MVP). El backend devuelve 422 si se intenta.
- **Solo una tool de negocio**: `info_empresa`. El resto del catálogo
  (Wave 1) viene después.
