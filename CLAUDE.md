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
ligero.** La definición completa de capas, gates y patrones está en
[`skills/enterprise-backend-fastapi/SKILL.md`](skills/enterprise-backend-fastapi/SKILL.md)
— **léelo antes de tocar código backend**.

Resumen de la triada por módulo:

```
app/modules/<feature>/
├── domain/         # Entities, interfaces (puertos), exceptions, value objects
├── application/    # DTOs, requests, responses, mappers, use cases
└── infrastructure/ # SQLAlchemy ORM, HTTP routes, LLM (sólo chat)
```

Para los patrones específicos de SAVI (módulo `chat`, MCP por turno,
soft branches, writers independientes, auto-título), ver
[`skills/savi-backend-patterns/SKILL.md`](skills/savi-backend-patterns/SKILL.md).

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
`claude-agent-sdk`). Tres acciones discriminadas en `POST /chat`:

- `send` (default): envía un mensaje nuevo.
- `edit_last`: reemplaza el último user activo y regenera. Supersede
  user + assistant viejos (soft branches).
- `regenerate`: regenera la última respuesta sin tocar el user.

Eventos SSE: `text_delta`, `thinking_delta`, `tool_use`, `tool_result`,
`superseded`, `title_update`, `done`, `error`. Auto-título en dos
fases con Haiku, persistencia con sessionmaker independiente que
sobrevive a la cancelación del cliente, metadata completa por turno
(`finish_reason`, `tool_invocations`, `usage`, `cost_usd`).

> **Todo el detalle** (anatomía del módulo, hard rules, decision gates,
> gotchas, plantillas para tools MCP nuevas) está en
> [`skills/savi-backend-patterns/SKILL.md`](skills/savi-backend-patterns/SKILL.md).
> Léelo antes de tocar el módulo `chat`.

Contrato hacia el frontend en [`backend/docs/FRONTEND_CHAT_SPEC.md`](backend/docs/FRONTEND_CHAT_SPEC.md).

---

## 6. Skills disponibles — qué leer antes de codear

Las skills viven en `skills/<nombre>/SKILL.md` y contienen patrones
detallados con ejemplos. **Lee la skill correspondiente ANTES de
generar código** — están escritas para que el LLM las consulte.

### Tabla de skills

| Skill                          | Descripción                                                            | Archivo                                                          |
|--------------------------------|------------------------------------------------------------------------|------------------------------------------------------------------|
| `commit-guides`                | Commits convencionales en español                                      | [SKILL.md](skills/commit-guides/SKILL.md)                        |
| `create-adaptable-composable`  | Composables Vue reutilizables y desacoplados                           | [SKILL.md](skills/create-adaptable-composable/SKILL.md)          |
| `frontend-shadcn-guide`        | Componentes shadcn-vue, convenciones de uso                            | [SKILL.md](skills/frontend-shadcn-guide/SKILL.md)                |
| `skill-creator`                | Crear nuevas skills para este proyecto                                 | [SKILL.md](skills/skill-creator/SKILL.md)                        |
| `tailwind-4`                   | `cn()`, clases utilitarias, Tailwind v4                                | [SKILL.md](skills/tailwind-4/SKILL.md)                           |
| `typescript`                   | Tipos const, interfaces planas, utility types                          | [SKILL.md](skills/typescript/SKILL.md)                           |
| `vue-best-practices`           | Composition API, `<script setup>`, SFC, composables                    | [SKILL.md](skills/vue-best-practices/SKILL.md)                   |
| `vue-debug-guides`             | Debugging de reactivity, watchers, lifecycle                           | [SKILL.md](skills/vue-debug-guides/SKILL.md)                     |
| `vue-pinia-best-practices`     | Stores, state, actions, getters con Pinia                              | [SKILL.md](skills/vue-pinia-best-practices/SKILL.md)             |
| `vue-router-best-practices`    | Rutas, guards, navegación programática                                 | [SKILL.md](skills/vue-router-best-practices/SKILL.md)            |
| `vue-testing-best-practices`   | Tests de componentes y composables                                     | [SKILL.md](skills/vue-testing-best-practices/SKILL.md)           |
| `zod-4`                        | Validaciones con Zod v4 (`z.email()`, `z.uuid()`)                      | [SKILL.md](skills/zod-4/SKILL.md)                                |

> Todas las skills viven en `skills/` del repo (versionadas con el código).
> Dos skills extra cubren la arquitectura empresarial de referencia
> (vienen versionadas también, originalmente publicadas como skills
> globales por @gentleman-programming):

| Skill                              | Descripción                                                                                              | Archivo                                                          |
|------------------------------------|----------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| `enterprise-backend-fastapi`       | Arquitectura backend de referencia: FastAPI + Clean/Hexagonal, use cases, repositorios, SQLAlchemy 2 async, Pydantic v2, uv | [SKILL.md](skills/enterprise-backend-fastapi/SKILL.md)           |
| `enterprise-frontend-architecture` | Arquitectura empresarial Vue 3: feature-based modules, vue-query, Pinia setup, shadcn-vue, axios HttpClient | [SKILL.md](skills/enterprise-frontend-architecture/SKILL.md)     |
| `savi-backend-patterns`            | Particularidades de SAVI: módulo chat, MCP por turno, soft branches, writers independientes, auto-título | [SKILL.md](skills/savi-backend-patterns/SKILL.md)                |

### Precedencia entre skills

Cuando varias skills aplican al mismo cambio, el orden de lectura es:

1. **Skill general** que da el marco arquitectónico
   (`enterprise-backend-fastapi`, `enterprise-frontend-architecture`).
2. **Skill específica** del proyecto (`savi-backend-patterns`) o del
   tema (`vue-pinia-best-practices`, `frontend-shadcn-guide`, etc.).
3. Si la específica contradice la general, **gana la específica** —
   está más cerca del caso real.

### Auto-invoke — qué skill leer antes de cada acción

**Backend (FastAPI + Clean Architecture)** — la app `backend/` del monorepo:

| Acción                                                                  | Skills (en orden)                                          |
|-------------------------------------------------------------------------|------------------------------------------------------------|
| Crear un module nuevo (`app/modules/<feature>/`)                        | `enterprise-backend-fastapi`                               |
| Crear un use case, repository, mapper o entity en module existente      | `enterprise-backend-fastapi`                               |
| Tocar cualquier archivo de `app/modules/chat/`                          | `enterprise-backend-fastapi` + `savi-backend-patterns`     |
| Añadir una tool MCP nueva                                               | `savi-backend-patterns`                                    |
| Diseñar endpoints REST / SSE en `infrastructure/http/`                  | `enterprise-backend-fastapi`                               |
| Modificar el flujo del turno (send/edit_last/regenerate/auto-título)    | `savi-backend-patterns`                                    |
| Agregar puertos (interfaces) y sus implementaciones                     | `enterprise-backend-fastapi` (+ `savi-backend-patterns` si afecta `chat`) |
| Generar o aplicar una migración Alembic                                 | `enterprise-backend-fastapi`                               |
| Persistencia que debe sobrevivir a la cancelación del cliente           | `savi-backend-patterns` (patrón sessionmaker independiente) |

**Frontend (Vue 3 + Tailwind + Vite)** — la app `frontend/` del monorepo:

| Acción                                                            | Skill                                |
|-------------------------------------------------------------------|--------------------------------------|
| Diseñar la arquitectura de un módulo nuevo en `src/modules/`      | `enterprise-frontend-architecture`   |
| Configurar `axios HttpClient`, `vue-query` o el setup de Pinia    | `enterprise-frontend-architecture`   |
| Crear el adapter / service / composable de un endpoint del backend | `enterprise-frontend-architecture`   |
| Crear o modificar componentes Vue                                 | `vue-best-practices`                 |
| Crear o modificar stores con Pinia                                | `vue-pinia-best-practices`           |
| Agregar rutas o guards de navegación                              | `vue-router-best-practices`          |
| Escribir tests de componentes o composables                       | `vue-testing-best-practices`         |
| Trabajar con componentes shadcn-vue                               | `frontend-shadcn-guide`              |
| Aplicar clases de Tailwind                                        | `tailwind-4`                         |
| Escribir tipos o interfaces TypeScript                            | `typescript`                         |
| Crear esquemas de validación con Zod                              | `zod-4`                              |
| Crear composables reutilizables y desacoplados                    | `create-adaptable-composable`        |
| Depurar problemas de reactividad, lifecycle o watchers            | `vue-debug-guides`                   |

> **Reglas críticas del frontend (NO negociables)**:
> - El consumer del SSE `POST /chat` está documentado en
>   `backend/docs/FRONTEND_CHAT_SPEC.md` — léelo antes de escribir el
>   código del chat.
> - **NUNCA muestres SQL crudo ni nombres internos de tools** al usuario
>   final. El backend ya devuelve respuestas interpretadas; si llega
>   alguna leak, es bug del backend.
> - Respeta `title_locked` (sin auto-rename si `true`) y `superseded_at`
>   (oculta del hilo activo por default).

**General (aplica a backend y frontend)**:

| Acción                          | Skill           |
|---------------------------------|-----------------|
| Crear un commit git             | `commit-guides` |
| Escribir un mensaje de commit   | `commit-guides` |
| Crear una nueva skill           | `skill-creator` |

> **Regla de oro de los commits — NO negociable**:
> **NUNCA hago commits por iniciativa propia.** Termino el trabajo,
> dejo claro qué cambió, propongo el mensaje, y **espero confirmación
> explícita del usuario** antes de ejecutar `git commit`. Ni siquiera
> aunque hayan pasado varias funcionalidades seguidas: el commit lo
> autoriza el usuario, no yo. Esto incluye los commits "obvios" de
> docs o lint — todos requieren OK.

---

## 7. Bases de datos

Dos pools async aislados (`app/infrastructure/database/pool.py`):

| Pool | Propósito | Permisos |
|---|---|---|
| `agent_db` | Datos del agente (conversaciones, mensajes, futuro auth) | RW |
| `erp_db` | ERP del cliente (lectura interpretada por SAVI) | **Read-only forzado** (`default_transaction_read_only=on` + `statement_timeout=60s`) |

Migración inicial Alembic ya creó las tablas `conversations` y `messages`
en el agente con `deleted_at` y `user_id` nullable para auth futura.

---

## 8. Entorno local (Windows + PowerShell)

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

### Pre-commit hook (instalar una sola vez tras clonar)

Desde la raíz del monorepo:

```powershell
uv tool install pre-commit            # o: pipx install pre-commit
pre-commit install                    # registra el hook en .git/hooks
```

Configurado en `.pre-commit-config.yaml`:

- **Backend** (`backend/**/*.py`): Ruff (lint + fix + format) + Pyright
  strict. Si falla, el commit se aborta.
- **Genéricos**: trailing whitespace, end-of-file-fixer, YAML/TOML
  válidos, sin archivos enormes (> 500 KB), sin merge conflicts.

Forzar sobre todos los archivos: `pre-commit run --all-files`.

---

## 9. Cómo se construye el agente

El runner está en `app/modules/chat/infrastructure/llm/runner.py` y
sigue los patrones documentados en
[`skills/savi-backend-patterns/SKILL.md`](skills/savi-backend-patterns/SKILL.md)
(hard rules + decision gates + anatomía del módulo `chat`).

Resumen del ciclo de un turno:

```
POST /chat (action) → ChatTurnUseCase.validate()  ← 422 si falla
                    → ChatTurnUseCase.execute()   ← async generator
                          ↳ runner.stream_turn(prompt)
                              ↳ build_savi_mcp_server() in-process
                              ↳ claude_agent_sdk.query()
                          ↳ _TurnAccumulator.consume(event)
                          ↳ asyncio.create_task(writer.write(msg))   ← sobrevive cancel
                          ↳ asyncio.create_task(title_updater.*)     ← sobrevive cancel
                    → StreamingResponse(SSE)
```

Detalles (cap de chars, retry en initialize-timeout, auto-título dos
fases, soft branches, etc.) en la skill — no los repito acá.

---

## 10. Decisiones tomadas (no rehacerlas sin razón)

- **No usar `anthropic` directo** — usar `claude-agent-sdk`. Ya está
  decidido y validado contra otro backend hermano.
- **MVP sin auth, sin RAG, sin permisos 3D.** El esqueleto está listo
  para meter cualquiera de los tres sin reescribir.
- **Frontend en chat separado**. El backend NUNCA se nombra al cliente
  más allá del API que expone.
- **`uvicorn` invocado como módulo Python** (`python -m uvicorn`) por
  el bug del trampoline de uv en este Windows.

---

## 11. Pendientes (en orden sugerido)

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

## 12. Convenciones de commits

> **⚠️ Los commits SIEMPRE los confirma el usuario.** No se hace
> `git commit` por iniciativa propia, ni siquiera al cerrar una
> funcionalidad. Termina el trabajo, muestra el resumen del diff,
> propone el mensaje, y espera el OK explícito antes de ejecutar.
> Esto aplica a TODOS los commits, incluso los "obvios" de docs o
> lint. Ver skill `commit-guides`.

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

## 13. Reglas estrictas para el asistente (tú, Claude)

- **NUNCA hago commits por iniciativa propia.** Aunque haya cerrado una
  funcionalidad completa, los commits los autoriza el usuario. Resumo
  qué cambió, propongo el mensaje, espero "sí / commit" explícito y
  recién ahí ejecuto `git commit`. Aplica a todos los commits — feat,
  fix, docs, chore.
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
- **SIEMPRE** lee la skill correspondiente (ver sección 6) ANTES de
  generar código en cualquier capa.
