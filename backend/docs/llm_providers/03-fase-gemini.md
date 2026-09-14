# Fase 3 — Integración de Gemini

> Parte de: [PRD — Proveedores de IA configurables](00-prd.md)
> Estado: **propuesta** · Depende de: [Fase 2](02-fase-configuracion-proveedores.md) · Habilita: [Fase 4](04-fase-interfaz-admin-y-e2e.md)

Gemini se suma como segundo proveedor con **paridad funcional completa**:
las tres acciones del chat, las 4 tools del ERP, el auto-título y el
consumo con costo. Se integra con el SDK oficial `google-genai` usando un
loop manual de *function calling* con streaming, que emite los mismos
eventos SSE que Claude. Al terminar, activar Gemini por API hace que el
siguiente turno lo use, y cada mensaje registra con qué proveedor y modelo
se generó.

---

## Resultado esperado

- [ ] `GeminiRunner` implementa `LLMRunner` y emite `text_delta`, `thinking_delta`, `tool_use`, `tool_result`, `done` y `error`.
- [ ] Las 4 tools se ejecutan desde el registro neutral de la [Fase 1](01-fase-tools-neutrales.md), con permisos por base, multi-BD y auditoría intactos.
- [ ] `GeminiTitleGenerator` implementa `TitleGenerator`.
- [ ] `GeminiProbe` valida la API key y lista modelos.
- [ ] `usage` y `cost_usd` se calculan desde `usage_metadata` y la tabla de precios de la config.
- [ ] `messages` persiste `provider` y `model` (migración).
- [ ] El descriptor de Gemini pasa a `implemented=True`.

## Fuera de alcance

- Pantalla de administración → [Fase 4](04-fase-interfaz-admin-y-e2e.md).
- Vertex AI y credenciales de GCP (solo Gemini Developer API por API key).
- Salidas multimodales (imágenes, audio), grounding con Google Search y code execution.
- Soporte MCP del SDK de Google: es experimental y ejecuta las tools por su cuenta, sin eventos ni límite de iteraciones (ver PRD).

---

## 1. Dependencia

- Agregar `google-genai` a `pyproject.toml`, **con la versión exacta fijada**
  (la última estable al momento de implementar) y actualizar `uv.lock`.
- Revisar si PyInstaller necesita `hiddenimports` para `google.genai`,
  igual que con `sqlglot`. Se confirma con `installer/build.ps1 -SkipInstaller`
  y arrancando el bundle.

## 2. `GeminiRunner` — el loop

Ubicación: `chat/infrastructure/llm/gemini/runner.py`.

### Construcción por turno

```python
client = genai.Client(api_key=provider.credential)   # por turno: la key puede cambiar
tools = build_savi_tools(conversation_id=..., allowed_modules=..., erp_database_id=...)

config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters_json_schema=t.parameters,
        ) for t in tools
    ])],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    thinking_config=types.ThinkingConfig(include_thoughts=True),  # ver §2.4
)
contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
```

- `prompt` es el mismo que recibe Claude: el historial ya formateado por
  `_format_history_block` más el mensaje nuevo. El caso de uso no cambia.
- `system_instruction` usa el **mismo** `SYSTEM_PROMPT`. Las reglas de
  confidencialidad y de rechazo de temas fuera del ERP aplican igual (RNF-02).

### Algoritmo

```
iteraciones = 0
repetir:
    iteraciones += 1
    partes_modelo = []
    llamadas = []

    stream = await client.aio.models.generate_content_stream(model, contents, config)
    por cada chunk:
        acumular usage_metadata del chunk (quedarse con el último por llamada)
        por cada part del candidato:
            partes_modelo.append(part)            # SIN modificar: lleva thought_signature
            si part.thought y part.text     → ThinkingDeltaEvent(text)
            si part.text (no thought)       → TextDeltaEvent(s) vía ResponseTruncator
            si part.function_call           → llamadas.append(part.function_call)

    si no hay llamadas: emitir DoneEvent y terminar

    contents.append(Content(role="model", parts=partes_modelo))
    respuestas = []
    por cada llamada, en orden:
        id = llamada.id o uuid4()
        emitir ToolUseEvent(id, name, args)
        resultado = await ejecutar_tool(llamada)     # ver §2.3
        emitir ToolResultEvent(id, is_error=resultado.is_error)
        respuestas.append(Part.from_function_response(name, response=...))
    contents.append(Content(role="user", parts=respuestas))

    si iteraciones == max_agent_turns:
        emitir TextDeltaEvent(aviso de límite) y DoneEvent(finish_reason="truncated")
        terminar
```

Reglas del loop:

| Regla | Por qué |
|---|---|
| Reenviar **todas** las partes del modelo tal como llegaron | Preserva las *thought signatures*. Perderlas degrada el razonamiento en varios pasos (riesgo R3 del PRD). |
| Ejecutar llamadas paralelas **en orden**, una a la vez | Las tools comparten engine del ERP y la auditoría de `consultar_libre`; el paralelismo no aporta en consultas de segundos. |
| Todas las `function_response` de una iteración van en **un solo** `Content` | Es lo que el modelo espera para llamadas paralelas. |
| `max_agent_turns` cuenta **iteraciones del loop**, no llamadas a tools | Equivale a `max_turns` del SDK de Claude. |
| El truncado por `max_response_chars` corta el texto visible, pero no el loop de tools | Mismo comportamiento que el runner de Claude. |

### 2.3 Ejecución de tools

- Se busca el `ToolSpec` por `name`. Un nombre desconocido devuelve
  `ToolResult(is_error=True)` al modelo sin romper el turno.
- Una excepción en el handler se captura, se loguea y vuelve al modelo como
  error: el modelo puede corregir el argumento y reintentar, como ocurre hoy
  con Claude.
- Traducción de `ToolResult` a `function_response`:

| `ToolResult` | `response` enviado a Gemini |
|---|---|
| `is_error=False` | `{"result": text}` |
| `is_error=True` | `{"error": text}` |

### 2.4 Thinking

- `thinking_config` **solo** se envía si el modelo lo soporta: el SDK
  documenta que enviarlo a un modelo sin *thinking* devuelve error.
- Criterio: el modelo elegido declara soporte al listar modelos (el campo
  exacto se confirma contra la respuesta real de `models.list` al
  implementar). Si no se puede determinar, se prueba con *thinking* y ante
  ese error puntual se reintenta la misma llamada sin él, una vez.

### 2.5 Fin de respuesta y errores

| Situación | Evento |
|---|---|
| Stream termina sin llamadas pendientes | `DoneEvent(finish_reason="complete")` |
| `finish_reason` de límite de tokens | `DoneEvent(finish_reason="truncated")` |
| `finish_reason` de seguridad o bloqueo | `ErrorEvent` con un mensaje neutral ("No pude generar una respuesta para esa consulta.") |
| Credencial inválida (401/403) | `ErrorEvent` vía `user_facing_error(..., provider="gemini")`, que apunta a la pantalla de proveedores |
| Límite de uso o servicio no disponible (429/503) **antes del primer token** | Un reintento con espera corta; si vuelve a fallar, `ErrorEvent` |
| Error después de haber emitido texto | `ErrorEvent`; lo ya emitido queda persistido como hoy (`finish_reason=error`) |

Los valores exactos del enum `FinishReason` y la jerarquía de excepciones
de `google.genai.errors` se confirman contra la versión fijada del SDK al
implementar. La tabla de arriba es el contrato de comportamiento.

## 3. Consumo y costo

### Mapeo a `TokenUsage`

`usage_metadata` se **suma** entre las iteraciones del loop: un turno con
dos llamadas a tools son tres requests facturados.

| `TokenUsage` | Desde `usage_metadata` de Gemini |
|---|---|
| `input_tokens` | `prompt_token_count − cached_content_token_count` |
| `output_tokens` | `candidates_token_count + thoughts_token_count` |
| `cache_read_input_tokens` | `cached_content_token_count` |
| `cache_creation_input_tokens` | `0` (Gemini no factura escritura de caché implícita) |

- Los campos ausentes cuentan como `0`.
- El pensamiento se factura como salida, por eso suma a `output_tokens`.

### Cálculo de costo

Función pura compartida — `chat/infrastructure/llm/pricing.py`:

```python
def compute_cost_usd(usage: TokenUsage, price: ModelPricing | None) -> float | None:
    if price is None:
        return None
    return (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_input_tokens * price.cache_read
        + usage.cache_creation_input_tokens * price.cache_write
    ) / 1_000_000
```

- El precio sale de `ActiveProvider.pricing[chat_model]`.
- **Sin precio cargado, `cost_usd` queda en `None`** y no en `0`: un cero
  haría creer que el uso fue gratis. Los KPIs de consumo ya tratan
  `cost_usd` como nullable (`coalesce`).
- Claude sigue usando `total_cost_usd` del SDK, que es más preciso.

## 4. Proveedor y modelo por mensaje

### Migración

| Tabla | Columna | Tipo | Nulabilidad |
|---|---|---|---|
| `messages` | `provider` | `String(32)` | NULL: los mensajes previos no se pueden atribuir con certeza |
| `messages` | `model` | `String(120)` | NULL |

- Sin backfill a `claude`: los mensajes previos casi seguro son de Claude,
  pero afirmarlo en un dato de auditoría no es correcto. La UI de consumo
  los muestra como "sin registrar".
- `DoneEvent` gana `provider` y `model`, y `_TurnAccumulator` los pasa al
  writer del mensaje. Los dos runners los completan.
- La respuesta de `GET /conversations/{id}` los expone por mensaje. El
  frontend actual no se rompe: son campos nuevos.

### Consumo

- `usage.per_user` y los KPIs **no se desglosan por proveedor en esta
  fase**: los totales siguen sumando todo.
- Los datos quedan persistidos para agregar ese desglose sin migrar.

## 5. Título y prueba de credencial

**`GeminiTitleGenerator`** — `chat/infrastructure/llm/gemini/title_generator.py`:

- Llamada única, sin streaming y sin tools, con `title_model`, el mismo
  prompt del título (`title_prompt.py`) y un límite corto de tokens de
  salida.
- Ante cualquier error devuelve `None` (contrato del puerto): el título
  provisional queda como está.

**`GeminiProbe`** — `llm_providers/infrastructure/probes/gemini_probe.py`:

- `client.aio.models.list()`: si responde, la key es válida y se devuelven
  los modelos que soportan `generateContent`.
- 401/403 → `ok=False` con "La API key de Gemini no es válida o no tiene
  permisos".
- Nunca levanta.

## 6. Descriptor y factory

- `ProviderDescriptor(gemini).implemented = True`.
- `LLMRunnerFactory` y `TitleGeneratorFactory` construyen los adaptadores de
  Gemini para `kind == "gemini"`.

---

## Estructura agregada

```
chat/infrastructure/llm/
├── pricing.py                  # NUEVO — compute_cost_usd
└── gemini/
    ├── runner.py               # GeminiRunner
    ├── title_generator.py      # GeminiTitleGenerator
    └── mapping.py              # usage_metadata → TokenUsage, ToolResult → function_response

llm_providers/infrastructure/probes/
└── gemini_probe.py
```

## Tests

El cliente de Gemini se inyecta por constructor para poder reemplazarlo
por un doble que devuelve streams guionados. Los tests unitarios no hacen
llamadas reales.

| Test | Verifica |
|---|---|
| `test_gemini_runner_text_only.py` | Texto en varios chunks → `TextDeltaEvent`s en orden + `DoneEvent` con usage. |
| `test_gemini_runner_tool_loop.py` | Llamada a tool → `ToolUseEvent` → handler ejecutado → `ToolResultEvent` → segunda iteración con respuesta final. Las partes del modelo se reenvían intactas. |
| `test_gemini_runner_parallel_calls.py` | Dos llamadas en una iteración: ejecución en orden y un solo `Content` de respuestas. |
| `test_gemini_runner_max_turns.py` | Alcanzar `max_agent_turns` corta con aviso y `finish_reason="truncated"`. |
| `test_gemini_runner_tool_error.py` | Handler que levanta o tool desconocida → `{"error": ...}` al modelo; el turno continúa. |
| `test_gemini_runner_errors.py` | 401 → mensaje de credencial; bloqueo de seguridad → mensaje neutral; 429 antes del primer token → un reintento. |
| `test_gemini_usage_mapping.py` | Mapeo de tokens, caché restada del input, suma entre iteraciones. |
| `test_pricing.py` | Cálculo exacto; sin precio → `None`. |
| `test_gemini_title_generator.py` | Limpieza del título; error → `None`. |
| `test_gemini_probe.py` | Key válida lista modelos; key inválida → `ok=False`, sin excepción. |
| `test_message_provider_model.py` | `provider`/`model` persistidos por el writer y expuestos en la respuesta. |

## Verificación

- [ ] Lint, typecheck y suite completa en verde.
- [ ] Migración aplicada en Postgres y verificada en ambos caminos de SQLite.
- [ ] Con una API key real de Gemini, por API (sin UI todavía):
  - [ ] activar Gemini y hacer `send` → respuesta con al menos una tool;
  - [ ] `edit_last` y `regenerate` funcionan;
  - [ ] el mensaje persistido tiene `provider="gemini"`, `model`, `usage` y `cost_usd` (si hay precio);
  - [ ] el auto-título se genera con el modelo de títulos;
  - [ ] volver a activar Claude → el siguiente turno usa Claude, sin reiniciar.
- [ ] `build.ps1 -SkipInstaller`: el bundle arranca y un turno con Gemini funciona.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Gemini arma mal los argumentos de `consultar_datos` (objeto anidado complejo). | Schema explícito (Fase 1). Si falla de forma recurrente, se evalúa aplanar los argumentos solo en el adaptador de Gemini, sin tocar el handler. |
| El modelo elige `consultar_libre` antes que `consultar_datos`. | La descripción ya lo indica. Se mide en el E2E de la Fase 4 y, si hace falta, se ajusta la descripción compartida (beneficia a ambos proveedores). |
| Costo del thinking más alto de lo esperado. | Queda visible en `output_tokens` y `cost_usd` por mensaje; se puede desactivar el thinking desde la config en una iteración posterior. |
