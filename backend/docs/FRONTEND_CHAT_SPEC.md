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
}
```

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

### `GET /conversations/{id}` — conversación + mensajes

**Respuesta `200`**:
```json
{
  "conversation": { ... Conversation },
  "messages": [ ... Message[] ordenados por created_at asc ]
}
```

Úsalo al abrir una conversación en el panel central para hidratar el
historial.

---

### `POST /chat` — enviar mensaje y recibir respuesta en stream

**Body**:
```json
{
  "conversation_id": "856d84c7-...",
  "message": "Hola, ¿cuál es el NIT de mi empresa?"
}
```

`message` requerido, 1–16000 chars. `conversation_id` requerido —
debes crear la conversación antes (paso anterior).

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

## 4. Comportamiento de SAVI a respetar en la UI

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

## 5. Stack sugerido para el frontend

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

## 6. Layout objetivo (referencia visual)

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

## 7. Cómo arrancar el backend (para probar el frontend en local)

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

## 8. Limitaciones conocidas del MVP

- **Sin auth**. El backend acepta cualquier request. No expongas el
  endpoint en internet hasta que entre auth.
- **Sin rate limit**. Una pestaña abierta puede gastar tokens rápido.
- **Sin regenerar / editar último mensaje**. Si lo necesitas en la UI
  ya, dímelo y lo agregamos.
- **Sin auto-título**. La conversación queda con
  `"Nueva conversación"` hasta que se cambie. Te puedo agregar un
  `POST /conversations/{id}/title` cuando estés listo.
- **Solo una tool de negocio**: `info_empresa`. El resto del catálogo
  (Wave 1) viene después.
