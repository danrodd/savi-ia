# Fase 1 — Tools neutrales y puertos del proveedor

> Parte de: [PRD — Proveedores de IA configurables](00-prd.md)
> Estado: **implementada** (2026-09-13) · Depende de: nada · Habilita: [Fase 2](02-fase-configuracion-proveedores.md)
> Ver [Hallazgos durante la implementación](#hallazgos-durante-la-implementación): se corrigieron dos defectos reales.

Refactor **sin cambio visible**: las tools del ERP pasan a tener una
definición neutral (sin SDK de por medio), el auto-título pasa a ser un
puerto, y el código propio de Claude se ordena como un adaptador más.
Al terminar, SAVI responde exactamente igual que hoy, pero sumar Gemini
ya no obliga a duplicar las tools ni a tocar el caso de uso del chat.

---

## Resultado esperado

- [ ] Las 4 tools se definen **una sola vez** en un registro neutral (`ToolSpec`).
- [ ] Claude consume ese registro a través de un adaptador MCP.
- [ ] El auto-título depende de un puerto `TitleGenerator`, no de una función de Claude.
- [ ] El truncado de respuestas y el mensaje de error de credencial son helpers compartidos.
- [ ] La suite actual sigue en verde y el chat se comporta idéntico (smoke E2E).

## Fuera de alcance

- Configuración en BD o por interfaz → [Fase 2](02-fase-configuracion-proveedores.md).
- Cualquier código de Gemini → [Fase 3](03-fase-gemini.md).
- Cambios en eventos SSE, persistencia o frontend.

---

## 1. Registro neutral de tools

### Qué hay hoy

`chat/infrastructure/llm/mcp/server.py` mezcla tres cosas:

| Qué | Acoplado a Claude |
|---|---|
| Nombre y descripción de cada tool | No (strings) |
| Schema de argumentos (`{"consulta": dict}`, `{"sql": str, ...}`) | Sí: formato del decorador `@tool` del SDK |
| Handler (`*_impl`) con clausuras por turno | No: recibe `dict` y devuelve `{"content": [...], "isError"?}` |

### Qué se construye

**Entidad de dominio** — `chat/domain/entities/tool_spec.py`:

```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str                        # "consultar_datos"
    description: str
    parameters: dict[str, Any]       # JSON Schema (draft 2020-12, subset)
    handler: Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class ToolResult:
    text: str
    is_error: bool = False
```

`ToolResult` es neutral: cada adaptador lo traduce a su formato (MCP para
Claude, `function_response` para Gemini).

**Registro por turno** — `chat/infrastructure/llm/tools/registry.py`:

```python
def build_savi_tools(
    *,
    conversation_id: UUID | None,
    allowed_modules: frozenset[ModuleCode] | None,
    erp_database_id: UUID | None,
) -> list[ToolSpec]: ...
```

- Se sigue construyendo **por turno** (misma regla que el MCP server hoy):
  las clausuras atan `conversation_id`, los módulos permitidos (D3) y la
  base del ERP consultada.
- Los `*_impl` actuales **no se modifican**. Un envoltorio convierte su
  respuesta MCP (`{"content": [{"type": "text", "text": ...}], "isError": ...}`)
  a `ToolResult`.
- Siguen siendo **exactamente 4 tools**. Ver
  [`mcp_deferred_tools_gotcha.md`](../mcp_deferred_tools_gotcha.md).

### JSON Schema explícito por tool

Hoy los schemas son laxos porque el SDK de Claude los tolera. Gemini
valida contra JSON Schema, así que se definen completos:

| Tool | Argumentos | Fuente de verdad del schema |
|---|---|---|
| `info_empresa` | ninguno (`{"type": "object", "properties": {}}`) | — |
| `consultar_datos` | `consulta`: objeto con `entidad`, `modo` (`agregado` \| `detalle` \| `registro`), `metricas`, `dimensiones`, `campos`, `filtros[{campo, op, valor}]`, `orden{campo, dir}`, `limite` | `data_query/domain/semantic_query.py` (`SemanticQuery`, `QueryMode`, `FilterOp`, `SortSpec`) |
| `consultar_libre` | `sql` (string, requerido), `pregunta_usuario` (string, requerido) | `mcp/tools/consultar_libre.py` |
| `consultar_conocimiento` | `tipo` (enum de 7 valores), `consulta` (string) | `mcp/tools/knowledge.py` y su descripción |

Reglas:

- Los enums (`modo`, `op`, `tipo`) se generan **desde los `StrEnum` del
  código**, no se copian a mano: si se agrega un valor al dominio, el
  schema lo refleja solo.
- `valor` de un filtro admite string, número, booleano o lista: se declara
  como tal y la validación fina queda en el compilador semántico, como hoy.
- Cada schema se cubre con un test que lo valida como JSON Schema.

## 2. Adaptador MCP para Claude

`chat/infrastructure/llm/claude/mcp_adapter.py`:

```python
def build_mcp_server(tools: list[ToolSpec]) -> McpSdkServerConfig: ...
def allowed_tool_names(tools: list[ToolSpec]) -> list[str]: ...  # "mcp__savi__<name>"
```

- Traduce cada `ToolSpec` a `@tool(name, description, parameters)` +
  `create_sdk_mcp_server`, y `ToolResult` de vuelta al formato MCP.
- `ALLOWED_TOOLS` deja de ser una lista escrita a mano: se deriva del
  registro. Así no se puede registrar una tool y olvidarse de habilitarla.
- **Verificado (2026-09-13):** en `claude-agent-sdk` 0.2.87 la firma es
  `tool(name, description, input_schema: type | dict[str, Any], annotations=None)`,
  así que acepta un `dict`. Queda por confirmar en runtime, con el smoke
  E2E, que un JSON Schema completo (con `type: object`, `properties` y
  `required`) llega intacto al modelo y no solo el formato abreviado
  `{"campo": tipo}`. Si no llegara, el adaptador traduce el schema; la
  definición neutral no cambia.

## 3. Puerto `TitleGenerator`

Hoy `SqlAlchemyConversationTitleUpdater` importa directo
`title_generator.generate_title` (Claude).

**Puerto** — `chat/domain/interfaces/title_generator.py`:

```python
class TitleGenerator(ABC):
    @abstractmethod
    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None: ...
```

- `ClaudeTitleGenerator` en `chat/infrastructure/llm/claude/title_generator.py`,
  con la lógica actual intacta (system prompt, limpieza, límite de 80
  caracteres, `None` ante error).
- El system prompt del título y `_clean` pasan a
  `chat/infrastructure/llm/title_prompt.py`, compartido entre proveedores.
- `SqlAlchemyConversationTitleUpdater` recibe el puerto por constructor.

## 4. Helpers compartidos

| Helper | Archivo | Qué extrae de `runner.py` |
|---|---|---|
| `ResponseTruncator` | `chat/infrastructure/llm/truncation.py` | Límite `max_response_chars` + aviso de truncado. Recibe texto y devuelve los `TextDeltaEvent` a emitir. |
| `user_facing_error(message, *, credential_remedy)` | `chat/infrastructure/llm/errors.py` | Detección de errores de credencial. Cada adaptador aporta su remedio: Claude sigue apuntando a "Iniciar sesión en Claude" (`CREDENTIAL_REMEDY` en `claude/runner.py`); en la Fase 4 se suma el de la pantalla de proveedores. |

`test_user_facing_error.py` se mueve con el helper y se mantiene.

## 5. Reorganización de archivos

```
chat/infrastructure/llm/
├── system_prompt.py            # sin cambios
├── title_prompt.py             # NUEVO — prompt y limpieza del título
├── truncation.py               # NUEVO
├── errors.py                   # NUEVO
├── tools/
│   ├── registry.py             # NUEVO — build_savi_tools()
│   ├── schemas.py              # NUEVO — JSON Schemas de las 4 tools
│   └── (impls actuales, movidos desde mcp/tools/ sin modificar)
└── claude/
    ├── runner.py               # antes llm/runner.py
    ├── title_generator.py      # antes llm/title_generator.py (ClaudeTitleGenerator)
    ├── mcp_adapter.py          # reemplaza mcp/server.py
    └── sdk_env.py              # entorno del CLI (antes duplicado en runner y título)
```

- `chat/infrastructure/http/dependencies.py` sigue construyendo
  `ClaudeAgentRunner` directamente (la factory llega en la Fase 2).
- `test_mcp_server_tool_limit.py` pasa a validar el registro neutral
  (sigue exigiendo ≤ 4 tools).

---

## Tests

Los archivos finales agrupan los tests previstos (schemas y normalización
de resultados en un solo archivo, título y puerto en otro):

| Test | Verifica |
|---|---|
| `test_tool_registry.py` | Exactamente las 4 tools; schemas válidos como JSON Schema; enums derivados de `QueryMode`, `FilterOp` y `KNOWLEDGE_TIPOS`; una consulta realista valida contra el schema de `consultar_datos`; normalización de resultados (formato MCP con `isError`, dict crudo del knowledge, error por `tipo` desconocido, excepción del handler). |
| `test_claude_mcp_adapter.py` | Ejecuta el `tools/call` real del MCP server del SDK: el knowledge le llega al modelo con contenido, los errores se marcan como error, y el JSON Schema completo se anuncia intacto. Nombres `mcp__savi__*`. |
| `test_mcp_server_tool_limit.py` | Límite de 4 tools, ahora sobre el registro neutral. |
| `test_user_facing_error.py` | Se mantiene, sobre el helper compartido. |
| `test_truncation.py` | Corte exacto en el límite, aviso único, nada después del corte. |
| `test_title_generation.py` | El title updater usa el puerto (con un doble) y persiste; limpieza y armado del prompt del título. |

## Verificación

- [x] `uv run lint` y `uv run typecheck` en verde.
- [x] `uv run pytest` en verde: 204 tests (183 previos + 21 nuevos), 1 skip preexistente.
- [x] Smoke E2E con Claude contra el ERP real (`farmacias_similares`):
      las 4 tools con datos reales (razón social, 19.866 terceros, 60
      usuarios), `edit_last` con `superseded`, `regenerate`, auto-título y
      `usage`/`cost_usd` persistidos.
- [x] Sin referencias a `claude_agent_sdk` fuera de `llm/claude/`.
- [x] `build.ps1 -SkipInstaller` compila, e incluye los 16 módulos de
      `llm/claude`, `llm/tools` y los helpers. El único "missing module" es
      `pydantic.BaseModel`, un falso positivo de PyInstaller ajeno al cambio.
      No se ejecutó `SAVI.exe`: abre el navegador y el ícono de bandeja.

## Hallazgos durante la implementación

### Defectos corregidos

Se verificaron ejecutando el handler `tools/call` real del MCP server de
`claude-agent-sdk` 0.2.87, no solo leyendo código:

| # | Defecto | Efecto | Corrección |
|---|---|---|---|
| 1 | El SDK solo convierte resultados con la clave `content`. `consultar_conocimiento` devuelve dicts crudos (`{"matches": [...]}`). | **El catálogo de conocimiento le llegaba vacío a Claude** (`content: []`). Es consistente con las respuestas del tipo "la herramienta no responde" que registra `mcp_deferred_tools_gotcha.md`. | `to_tool_result` serializa el dict a texto para cualquier proveedor. |
| 2 | Las tools marcan error con `isError` y el SDK lee `is_error`. | Ningún error de tool se reportaba como error (`is_error=False` siempre). | El adaptador MCP emite `is_error`; el registro acepta ambas grafías. |

Cambio de comportamiento, a propósito: estos dos defectos eran parte del
comportamiento previo. Además, una excepción dentro de un handler ahora
vuelve al modelo como error de tool en lugar de propagarse.

### `ToolSearch` en cada turno (preexistente, fuera de esta fase)

El smoke mostró `ToolSearch` antes de cada tool, que es el modo *deferred
tools*. Se descartó que lo introdujera el refactor: el código anterior
(HEAD, en un worktree aparte) produjo la misma secuencia.

Causa probable: el CLI que lanza SAVI carga la configuración global de
Claude Code del equipo (`~/.claude`: plugins, hooks y servidores MCP del
usuario). El log lo muestra ejecutando un hook `SessionEnd` de un plugin
ajeno a SAVI. Esas tools extra empujan al SDK al modo deferred aunque SAVI
registre solo 4.

- Afecta a cualquier equipo donde el usuario tenga Claude Code configurado.
  Probablemente no a un equipo de cliente limpio.
- Posible corrección (a validar aparte): aislar el CLI con las opciones
  `setting_sources` y `strict_mcp_config` de `ClaudeAgentOptions`.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Un schema más estricto hace que Claude deje de llamar bien a `consultar_datos`. | Smoke E2E de las 4 tools antes de commitear; si Claude empeora, el adaptador MCP sigue pasando el schema abreviado actual. |
| Mover archivos rompe imports del empaquetado (PyInstaller). | `build.ps1 -SkipInstaller` al final de la fase para confirmar que el bundle arranca. |
