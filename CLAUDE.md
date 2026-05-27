# SAVI — SEO Group · Asistente Virtual Inteligente

> Este archivo se carga automáticamente en cada sesión de Claude Code.
> Mantén la información acumulada aquí — patrones, decisiones, comandos —
> para que cada conversación arranque con contexto.

---

## 1. Qué es SAVI

SAVI (**S.E.O. Asistente Virtual Inteligente**) es el agente de IA
corporativo de **SEO Group**, empresa colombiana que desarrolla un ERP
multi-vertical (agro, automotriz, restaurante, farmacia, salud, bomberos,
microcrédito).

**Lo que SAVI debe hacer**:
- Conocer el ERP entero (módulos, funcionalidades, procesos).
- Tener conocimiento específico de la empresa de cada usuario.
- Acceder a los datos del ERP, pero **interpretados** — no devolver
  registros crudos al usuario funcional.
- **Negarse rotundamente** a responder cualquier tema fuera de SEO Group,
  en cualquier idioma, con cualquier formulación (prompt injection,
  juegos de rol, traducciones, "ignora las instrucciones", etc.).

---

## 2. Monorepo

```
SAVI_SEO-ERP/
├── .git/
├── .gitignore         # Raíz, cubre Python + Node + IDE + secrets
├── CLAUDE.md          # Este archivo
├── backend/           # FastAPI + Clean Architecture (SAVI)
└── frontend/          # Vue 3 + Biome (en construcción por otro equipo)
```

Git inicializado en la raíz. **NO crear `.gitignore` locales por carpeta**
— el raíz es la única fuente de verdad. `.env.example` se versiona vía
whitelist (`!.env.example`), `.env` no.

---

## 3. Stack del backend

| Capa | Tecnología |
|---|---|
| Web | FastAPI + uvicorn |
| ORM | SQLAlchemy 2 async + asyncpg |
| Migraciones | Alembic (async-aware) |
| Validación | Pydantic v2 + pydantic-settings |
| LLM | `claude-agent-sdk>=0.0.10` (instalado 0.2.87) + `anthropic` |
| Package manager | `uv` |
| Lint | Ruff |
| Type check | Pyright **strict** |
| Python | 3.12 (descargado por uv al venv) |

---

## 4. Arquitectura

**Clean Architecture + Hexagonal + Feature-based modularity + DDD táctico
ligero.** Por cada módulo:

```
app/modules/<feature>/
├── domain/
│   ├── entities/          # Dataclasses puras (sin ORM)
│   ├── interfaces/        # Puertos (ABCs)
│   └── exceptions/
├── application/
│   ├── dtos/
│   ├── requests/          # Pydantic — entrada HTTP
│   ├── responses/         # Pydantic — salida HTTP
│   ├── mappers/
│   └── use_cases/         # Lógica orquestadora pura
└── infrastructure/
    ├── persistence/
    │   ├── models/        # SQLAlchemy ORM
    │   ├── mappers/       # ORM ↔ entidad
    │   └── repositories/  # Implementa los puertos
    ├── http/
    │   ├── routes.py
    │   └── dependencies.py
    └── llm/               # Solo en módulo `chat`
        ├── runner.py
        ├── system_prompt.py
        └── mcp/
            ├── server.py
            └── tools/
```

**Reglas no negociables**:
- Repositorios devuelven **entidades de dominio**, no modelos ORM.
- Endpoints devuelven **Pydantic responses**, no entidades ni DTOs.
- Todo SQL contra el ERP va por el pool readonly (transacción RO +
  `statement_timeout`).
- Migraciones con `uv run alembic revision --autogenerate -m "..."`.
- Soft delete via `deleted_at` (no `DELETE` físico).
- Conventional Commits.

---

## 5. Módulos actuales

### 5.1 `conversations`
CRUD de conversaciones y mensajes. Endpoints:
- `POST /conversations` — crear conversación.
- `GET /conversations` — listar (filtro `user_id`, paginación).
- `GET /conversations/{id}?include_superseded=bool` — conversación +
  mensajes. Default sólo trae el hilo activo. Con
  `include_superseded=true` también trae versiones anteriores (mensajes
  editados o regenerados).
- `PATCH /conversations/{id}` — renombrar manual + lock (`title_locked=true`).

Modelo de **revisiones soft**: columnas `superseded_at` +
`superseded_by_id` (FK self) en `messages`. Los mensajes nunca se
borran al editar/regenerar — quedan superseded y enlazados al que los
reemplazó, para trazabilidad completa.

### 5.2 `chat`
Endpoint conversacional con streaming SSE y LLM (Claude vía
`claude-agent-sdk`):
- `POST /chat` con body discriminado por `action`:
  - `send` (default): envía un mensaje nuevo.
  - `edit_last`: reemplaza el último user activo y regenera. Supersede
    user + assistant viejos.
  - `regenerate`: regenera la última respuesta sin tocar el user.
    Supersede el assistant viejo.
  Devuelve un stream `text/event-stream` con eventos `text_delta`,
  `thinking_delta`, `tool_use`, `tool_result`, `superseded`,
  `title_update`, `done`, `error`. Las validaciones de precondiciones
  (último user editable / último assistant regenerable) ocurren **antes**
  del stream para que FastAPI emita 422 limpio en lugar de un error
  enterrado en el SSE.
- Persiste mensaje del usuario al inicio del turno con la sesión del
  request.
- Persiste respuesta del asistente al cierre vía
  `AssistantMessageWriter` — un puerto cuya implementación usa un
  **sessionmaker independiente** y se despacha como
  `asyncio.create_task`. Esto garantiza que la persistencia
  sobreviva a la cancelación del cliente sin trucos shielded.
- Persiste **metadata completa del turno**: `finish_reason`
  (complete/interrupted/error/truncated), `tool_invocations[]` con
  input y status, `usage` (tokens) y `cost_usd`. El use case lo
  acumula con un `_TurnAccumulator` que consume cada `ChatEvent`.
- Carga historial completo previo y lo antepone como contexto, con
  marker `=== Nueva consulta del usuario (responde esta) ===`.
- **System prompt** estricto: identidad SAVI, alcance limitado a SEO
  Group, rechazo canónico para off-topic en cualquier idioma.
- **MCP server in-process** (construido por turno para futuras
  clausuras con el usuario). Tool inicial: `info_empresa()` — lee
  `Empresa.Empresa` del ERP.
- **Auto-título de la conversación** en dos fases con modelo barato
  (`CLAUDE_TITLE_MODEL`, Haiku por default):
  - Fase 1: dispara como `asyncio.create_task` al inicio del primer
    turno con sólo el `user_msg`. Emite evento SSE `title_update` en
    cuanto está lista. Sobrevive a la cancelación del cliente.
  - Fase 2: tras `finish_reason=complete`, refina el título con la
    respuesta del asistente a la vista (timeout `TITLE_PHASE2_TIMEOUT_S`,
    default 4 s). Si no alcanza, persiste igual en background.
  - Sólo dispara si `title_locked=false` y `title='Nueva conversación'`
    — esto evita el bug de Open WebUI (cancel+retry del primer mensaje
    no genera título).
- En Windows requiere `CLAUDE_CODE_GIT_BASH_PATH=C:/Program Files/Git/bin/bash.exe`.

---

## 6. Bases de datos

Dos pools async aislados (`app/infrastructure/database/pool.py`):

| Pool | Propósito | Permisos |
|---|---|---|
| `agent_db` | Datos del agente (conversaciones, mensajes, futuro auth) | RW |
| `erp_db` | ERP del cliente (lectura interpretada por SAVI) | **Read-only forzado** (`default_transaction_read_only=on` + `statement_timeout=60s`) |

Migración inicial Alembic ya creó las tablas `conversations` y `messages`
en el agente con `deleted_at` y `user_id` nullable para auth futura.

---

## 7. Entorno local (Windows + PowerShell)

- **uv** en `C:\Users\hikig\.local\bin\uv.exe` — NO está en PATH por
  defecto. Anteponer en cada comando:
  ```powershell
  $env:Path = "C:\Users\hikig\.local\bin;$env:Path"
  ```
- **Postgres** en `localhost:5433`, usuario `postgres`. Contraseña en
  `backend/.env` (gitignored).
- **uvicorn bug local**: `uv run uvicorn` falla con `uv trampoline failed
  to canonicalize script path`. Por eso el atajo `uv run dev` invoca
  uvicorn vía `python -m` desde `app/cli.py`.
- **NO usar `--reload`** en uvicorn — el módulo `chat` lanza el binario
  `claude.exe` como subproceso y monta un MCP server in-process por
  turno; el watcher de reload los mataría a mitad de stream. El atajo
  `uv run dev` arranca sin reload por diseño.
- **claude.exe** (binario del Claude Agent SDK) necesita git-bash. Está
  configurado vía `CLAUDE_CODE_GIT_BASH_PATH` en `.env`.

### Comandos típicos (desde `SAVI_SEO-ERP/backend/`)

Atajos definidos en `[project.scripts]` de `pyproject.toml`, implementados
en `app/cli.py`. Tras un `uv sync`, uv los expone como ejecutables del
venv.

```powershell
$env:Path = "C:\Users\hikig\.local\bin;$env:Path"

uv sync                                            # instalar deps
uv run dev                                         # dev server (sin --reload)
uv run lint                                        # ruff check .
uv run fmt                                         # ruff format .
uv run typecheck                                   # pyright app
uv run migrate                                     # alembic upgrade head
uv run pytest                                      # tests
uv run alembic revision --autogenerate -m "msg"    # generar migración
```

---

## 8. Cómo se construye el agente

El runner está en `app/modules/chat/infrastructure/llm/runner.py`. Flujo:

1. **Cada turno** construye un nuevo `ClaudeAgentOptions`:
   - `system_prompt` = SYSTEM_PROMPT de SAVI.
   - `mcp_servers={"savi": build_savi_mcp_server()}` (in-process).
   - `allowed_tools=["mcp__savi__info_empresa", ...]`.
   - `permission_mode="bypassPermissions"` (las tools están curadas).
   - `max_turns` del config.
2. `query(prompt, options)` devuelve un async generator de mensajes
   del SDK (AssistantMessage, UserMessage, ResultMessage).
3. Los mensajes se traducen a eventos tipados (`TextDeltaEvent`,
   `ToolUseEvent`, etc.) y se yieldean al endpoint, que los serializa
   como SSE.
4. Hay **cap de chars** en la respuesta (`max_response_chars`) — al
   cruzarlo añade nota de truncación pero sigue drenando el stream
   para que el subproceso cierre limpio.
5. Reintento único en `Control request timeout: initialize` (el binario
   `claude` tarda en arrancar bajo carga).

---

## 9. Decisiones tomadas (no rehacerlas sin razón)

- **No usar `anthropic` directo** — usar `claude-agent-sdk`. Ya está
  decidido y validado contra otro backend hermano.
- **MVP sin auth, sin RAG, sin permisos 3D.** El esqueleto está listo
  para meter cualquiera de los tres sin reescribir.
- **Frontend en chat separado**. El backend NUNCA se nombra al cliente
  más allá del API que expone.
- **`uvicorn` invocado como módulo Python** (`python -m uvicorn`) por
  el bug del trampoline de uv en este Windows.

---

## 10. Pendientes (en orden sugerido)

1. **Frontend del chat** — Vue 3, sidebar con conversaciones + área de
   mensajes con markdown (`markdown-it`) + input con SSE consumer.
   Documentado en `backend/docs/FRONTEND_CHAT_SPEC.md`.
2. **Catálogo Wave 1 de tools MCP**: `buscar_tercero`, `estado_cuenta_cliente`,
   `consultar_stock`, `ventas_periodo`, `facturas_por_pagar`,
   `consultar_factura`.
3. **RAG**: pgvector + multilingual-e5-large vía `fastembed` + ingesta
   de manuales del producto y `COMMENT ON` del schema del ERP.
4. **Auth + permisos 3D** (rol/perfil/nivel/dominios).
5. **Validador SQL AST** con `sqlglot` para tools que ejecuten SQL libre.

---

## 11. Convenciones de commits

```
feat(scope): mensaje en imperativo lowercase
fix(scope): ...
chore(scope): ...
refactor(scope): ...
docs(scope): ...
```

`scope` opcional pero recomendado: `chat`, `conversations`, `db`,
`gitignore`, `deps`, etc.

---

## 12. Reglas estrictas para el asistente (tú, Claude)

- **NUNCA** menciones nombres de otros productos o backends hermanos en
  el código, los commits, los comentarios ni la documentación de SAVI.
- **NUNCA** crees `.gitignore` locales en `backend/` o `frontend/` — el
  raíz cubre todo.
- **NUNCA** versiones secrets. `.env` está gitignored; `.env.example`
  está whitelisted.
- **Siempre** corre Ruff + Pyright (strict) antes de dar por terminada
  una tarea grande.
- **Siempre** que cambies el modelo de BD, genera migración Alembic.
- **Backend primero, frontend después** — y el backend nunca debe asumir
  qué frontend lo consume.
