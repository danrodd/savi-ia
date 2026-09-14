# Fase 5 — Integración de OpenAI

> Parte de: [PRD — Proveedores de IA configurables](00-prd.md)
> Estado: **propuesta** · Depende de: [Fase 4](04-fase-interfaz-admin-y-e2e.md)

OpenAI se suma como tercer proveedor con la misma paridad funcional que
Gemini: las tres acciones del chat, las cuatro tools del ERP, el auto-título,
streaming, trazabilidad de consumo y costo. La integración usará el SDK oficial
`openai` y la **Responses API**, no Chat Completions, porque Responses es la API
actual para streaming, function calling y modelos de razonamiento.

La implementación debe conservar el límite de SAVI: OpenAI solo ejecuta las
tools después de que el adaptador las traduzca desde el registro neutral y
después de que el runner emita los eventos de auditoría del turno.

---

## Resultado esperado

- [ ] `OpenAIRunner` implementa `LLMRunner`.
- [ ] `OpenAITitleGenerator` implementa `TitleGenerator`.
- [ ] `OpenAIProbe` valida la API key y lista modelos disponibles.
- [ ] El catálogo excluye modelos claramente incompatibles con texto y tools
      (embeddings, imágenes, audio, realtime, moderación y transcripción), pero
      conserva modelos desconocidos para no romperse cuando OpenAI agregue IDs.
- [ ] La interfaz marca un modelo recomendado y permite cambiarlo.
- [ ] Las cuatro tools funcionan con function calling controlado.
- [ ] `send`, `edit_last` y `regenerate` emiten los mismos eventos SSE que los
      proveedores existentes.
- [ ] Los items de razonamiento necesarios para continuar un tool loop se
      conservan, pero nunca se envía chain-of-thought al usuario.
- [ ] `usage`, `cost_usd`, `provider` y `model` se persisten igual que con
      Gemini.
- [ ] El proveedor se puede activar y desactivar sin reiniciar.
- [ ] El checklist E2E completo pasa con OpenAI activo.

## Fuera de alcance

- Azure OpenAI, endpoints compatibles de terceros, `base_url` configurable y
  autenticación Entra ID.
- OAuth, sesiones locales o credenciales distintas de API key.
- Built-in tools de OpenAI como web search, file search, computer use o code
  interpreter. SAVI solo habilita sus cuatro tools del ERP.
- Conversaciones persistidas en OpenAI mediante `previous_response_id` o
  `store=true`. El historial sigue siendo propiedad de SAVI.
- Enrutamiento automático entre proveedores. El fallback de esta fase solo
  cambia de modelo dentro de OpenAI y debe ser explícitamente configurable.
- Soporte multimodal de entrada y salida.

---

## 1. Dependencia y configuración

Agregar al backend una versión exacta de `openai` y actualizar `uv.lock`.
La versión se fija contra la API pública usada por los tests, no contra una
dependencia transitiva.

### Descriptor

`ProviderDescriptor(openai)` debe declarar:

| Campo | Valor |
|---|---|
| `kind` | `openai` |
| `display_name` | `OpenAI` |
| `credential_kinds` | `api_key` |
| `supports_model_listing` | `true` |
| `implemented` | `true` al finalizar la fase |

La API key entra por la pantalla de administración y se cifra en reposo con el
mismo `FernetCredentialCipher`. Nunca se copia a `os.environ`, logs, eventos
SSE, respuestas HTTP ni reportes de diagnóstico.

### Settings de resiliencia

Agregar settings equivalentes a Gemini, con defaults conservadores:

- `OPENAI_RETRY_ATTEMPTS` para errores `429` y `5xx` antes del primer token.
- `OPENAI_RETRY_BASE_DELAY_S` para backoff exponencial.
- `OPENAI_FALLBACK_MODELS`, lista separada por comas y vacía por defecto.

Un modelo fallback nunca se elige por nombre inventado. Debe provenir de la
configuración o de un modelo seleccionado por el administrador.

---

## 2. `OpenAIProbe`

Ubicación:

```text
backend/app/modules/llm_providers/infrastructure/probes/openai_probe.py
```

Usar `AsyncOpenAI(api_key=credential)` por operación. El probe implementa:

```python
async def test(config: LlmProviderConfig) -> ProbeResult: ...
async def list_models(config: LlmProviderConfig) -> list[ModelInfo]: ...
```

### Listado

`client.models.list()` devuelve los modelos visibles para la organización de la
API key. El endpoint no debe tratar el catálogo como garantía de que cada
modelo permite el mismo conjunto de capacidades; por eso:

- se eliminan únicamente familias inequívocamente no conversacionales;
- se conservan IDs desconocidos para soportar modelos futuros;
- `display_name` usa el ID cuando el endpoint no entrega nombre amigable;
- se ordena de forma estable por nombre visible e ID;
- nunca se muestran modelos de otra credencial ni se persiste el catálogo.

La recomendación final se hace en frontend sobre el catálogo devuelto. El
heurístico debe preferir modelos generales de texto, evitar embeddings,
imagen, audio, realtime, preview y moderación, y reconocer familias `gpt` y

### Prueba de credencial

Con modelos vacíos, `test` valida la API key mediante `models.list()` y devuelve
el catálogo. Con un modelo seleccionado, puede ejecutar una solicitud mínima
de Responses para comprobar que ese modelo está habilitado para la cuenta.

Resultados esperados:

| Situación | Resultado |
|---|---|
| `401`/`403` | `ok=false`, detalle accionable para actualizar la API key |
| `429` | `ok=false` o retry acotado, nunca excepción sin mapear |
| `5xx`/timeout | `ok=false` con indisponibilidad temporal |
| catálogo válido | `ok=true` con `models` |
| catálogo vacío | `ok=true` solo si la API respondió; la UI permite IDs manuales |

El probe nunca levanta una excepción de red hacia HTTP.

---

## 3. `OpenAIRunner` — Responses API

Ubicación:

```text
backend/app/modules/chat/infrastructure/llm/openai/runner.py
```

### Cliente por turno

```python
client = AsyncOpenAI(api_key=provider.credential)
tools = build_savi_tools(
    conversation_id=conversation_id,
    allowed_modules=allowed_modules,
    erp_database_id=erp_database_id,
)
```

El runner usa el mismo `SYSTEM_PROMPT` y el mismo prompt con historial que
Claude y Gemini. No usa `previous_response_id` ni `store=true`: SAVI conserva
el historial, el aislamiento entre clientes y la auditoría.

### Traducción de tools

Cada `ToolSpec` se convierte en una función de Responses:

```python
{
    "type": "function",
    "name": tool.name,
    "description": tool.description,
    "parameters": tool.parameters,
    "strict": False,
}
```

La primera implementación usa `strict=false` porque las schemas neutrales de
SAVI pueden contener campos opcionales y estructuras que no cumplen todos los
requisitos de strict mode. La fase debe agregar un test que pruebe strict mode
por tool y solo activarlo cuando la transformación sea semánticamente segura.

### Loop manual

```text
input = [mensaje de usuario con el historial formateado]
iteraciones = 0

repetir hasta max_agent_turns:
    response = Responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=input,
        tools=tools,
        stream=True,
        store=False,
    )

    output_items = []
    calls = []
    por cada evento:
        response.output_text.delta -> TextDeltaEvent
        response.function_call_arguments.delta -> acumular argumentos
        response.function_call_arguments.done -> completar llamada
        response.output_item.done -> conservar item completo
        response.completed -> acumular usage y finish_reason

    si no hay calls:
        emitir DoneEvent y terminar

    agregar a input todos los output_items completos de la respuesta
    por cada call en el orden recibido:
        emitir ToolUseEvent(call.id, call.name, args)
        resultado = await handler(args)
        emitir ToolResultEvent(call.id, resultado.is_error)
        input.append({
            "type": "function_call_output",
            "call_id": call.call_id,
            "output": resultado.text,
        })

    incrementar iteraciones
```

### Reglas críticas del loop

- No reenviar solo el texto visible: se conservan todos los output items que
  OpenAI exige para continuar respuestas de razonamiento con tools.
- No mostrar reasoning tokens ni contenido de razonamiento interno al usuario.
- Las llamadas de tools se ejecutan secuencialmente, aunque Responses pueda
  devolver varias en una respuesta. Esto conserva el orden de auditoría y el
  aislamiento del engine ERP.
- Todas las respuestas de tools se agregan como `function_call_output` con el
  `call_id` exacto, nunca con el nombre como identificador.
- Un nombre desconocido o una excepción del handler se devuelve al modelo como
  error de tool y no rompe el proceso del turno.
- `max_agent_turns` cuenta respuestas del modelo, no cantidad de llamadas.
- El truncado de texto visible no detiene el loop de tools.
- Si hay texto visible y luego falla el proveedor, se conserva el texto parcial
  y se termina con `finish_reason="error"`.

### Eventos

| Evento OpenAI | Evento SAVI |
|---|---|
| `response.output_text.delta` | `TextDeltaEvent` |
| resumen de razonamiento explícitamente permitido | `ThinkingDeltaEvent`, opcional |
| `response.output_item.added`/`done` para function call | preparación interna de `ToolUseEvent` |
| `response.function_call_arguments.done` | `ToolUseEvent` |
| handler terminado | `ToolResultEvent` |
| `response.completed` | `DoneEvent` |
| error HTTP, stream o safety | `ErrorEvent` |

---

## 4. Razonamiento y seguridad

OpenAI puede devolver items de razonamiento asociados a function calls. El
adaptador debe reenviarlos según el contrato de Responses, pero:

- nunca emite el contenido privado como `ThinkingDeltaEvent`;
- solo puede emitir un resumen explícito si la API lo devuelve como resumen
  seguro y el contrato de producto lo permite;
- no registra reasoning tokens ni contenido de razonamiento en logs;
- conserva `encrypted_content` cuando sea necesario para el siguiente request;
- prueba un modelo con razonamiento y una tool para comprobar que el segundo
  request no falla por haber perdido items de contexto.

Las reglas de rechazo fuera del ERP, confidencialidad de tools, modelo,
proveedor e infraestructura siguen siendo las del mismo `SYSTEM_PROMPT`.

---

## 5. Usage y costo

Ubicación sugerida:

```text
backend/app/modules/chat/infrastructure/llm/openai/mapping.py
```

Mapeo esperado desde `response.usage`:

| `TokenUsage` | OpenAI Responses |
|---|---|
| `input_tokens` | `input_tokens - input_tokens_details.cached_tokens` |
| `output_tokens` | `output_tokens`, incluyendo reasoning tokens si vienen dentro del total |
| `cache_read_input_tokens` | `input_tokens_details.cached_tokens` |
| `cache_creation_input_tokens` | `0` salvo que una capacidad futura lo exponga explícitamente |

El uso se suma por cada request del loop, porque cada vuelta puede ser
facturable. `compute_cost_usd` calcula el costo desde los precios configurados
por el administrador. Sin precio, `cost_usd` queda en `null`.

`DoneEvent` debe contener siempre:

- `provider="openai"`;
- el ID del modelo realmente usado;
- usage canónico;
- costo nullable;
- finish reason normalizado a `complete`, `truncated` o `error`.

---

## 6. Títulos

Ubicación:

```text
backend/app/modules/chat/infrastructure/llm/openai/title_generator.py
```

- Solicitud única a Responses API.
- Sin tools.
- `store=false`.
- Usa `title_model` y el prompt compartido de títulos.
- Límite corto de salida.
- Limpia el resultado con los helpers existentes.
- Devuelve `None` ante timeout, error de credencial, safety block o respuesta
  inválida.
- No emite eventos SSE.

---

## 7. Resiliencia

El runner sigue el patrón de Gemini, pero sin fallback cruzado:

- reintenta `429` y `5xx` solo antes del primer token;
- usa backoff exponencial acotado;
- después de agotar retries prueba los modelos de
  `OPENAI_FALLBACK_MODELS` en orden;
- no cambia de modelo después de emitir texto;
- no reintenta errores `400`, `401`, `403` ni schemas inválidas;
- `401`/`403` devuelve un mensaje para actualizar la credencial;
- `429` agotado devuelve indisponibilidad temporal, no un 500;
- ningún retry incluye la API key en el mensaje de error.

---

## 8. Integración de aplicación

Cambios esperados:

```text
ProviderKind.OPENAI
ProviderDescriptor(openai)
OpenAIProbe
OpenAIRunner
OpenAITitleGenerator
OpenAI mapping
LLMRunnerFactory: openai
TitleGeneratorFactory: openai
DI de probes: openai
frontend LlmProviderKind: openai
frontend model recommendation: vocabulario gpt/o
```

No se modifica `ChatTurnUseCase`, el registro neutral de tools, el writer de
mensajes ni el esquema de usage. Si el contrato de OpenAI exige campos nuevos,
se adaptan dentro de `openai/` antes de tocar modelos compartidos.

---

## 9. Tests unitarios

El cliente OpenAI se inyecta por constructor. Ningún test unitario hace llamadas
reales.

| Test | Verifica |
|---|---|
| `test_openai_probe.py` | catálogo, filtrado, normalización, 401/403, timeout y key inválida |
| `test_openai_runner_text.py` | deltas de texto y `DoneEvent` |
| `test_openai_runner_tool_loop.py` | function call, handler, output item y segunda respuesta |
| `test_openai_runner_multiple_tools.py` | orden y `call_id` de varias llamadas |
| `test_openai_runner_reasoning.py` | preservación de items de razonamiento sin filtrarlos al usuario |
| `test_openai_runner_max_turns.py` | truncamiento después del límite |
| `test_openai_runner_errors.py` | auth, 400, safety, 429, 5xx y retries |
| `test_openai_runner_fallback.py` | fallback solo antes del primer token y modelo efectivo |
| `test_openai_usage_mapping.py` | input, output, reasoning incluido y cache read |
| `test_openai_title_generator.py` | prompt, modelo, limpieza y error → `None` |
| `test_message_provider_model.py` | persistencia de `openai` y modelo efectivo |
| `test_no_credential_leak.py` | key ausente en response, logs y diagnóstico |

---

## 10. E2E completo

La fase se considera terminada solo cuando el checklist de OpenAI pasa, además
de conservar Claude y Gemini.

### Administración

- Configurar una API key válida y listar modelos.
- Ver un modelo recomendado entre un catálogo grande.
- Buscar un modelo por ID.
- Elegir modelos distintos para chat y títulos.
- Guardar precios y comprobar costo calculado.
- API key inválida → detalle legible sin persistirla.
- Activar OpenAI con confirmación explícita.
- Cambiar entre OpenAI, Gemini y Claude sin reiniciar.
- Confirmar que ninguna respuesta, pantalla o log contiene la key.

### Chat

- `send` de texto.
- `edit_last`.
- `regenerate`.
- Streaming con múltiples `text_delta`.
- Consulta fuera del ERP → rechazo canónico.
- Solicitud del system prompt, tools, modelo o proveedor → no revela
  infraestructura.
- Error temporal OpenAI → retries y fallback observables en diagnóstico, no en
  el texto del usuario.

### Tools y permisos

- `info_empresa`.
- `consultar_datos`.
- `consultar_libre` con auditoría.
- `consultar_conocimiento`.
- Filtrado por módulos autorizados.
- Conversación contra otro cliente ERP.
- Base desactivada → `erp_database_unavailable`.

### Título, consumo y cancelación

- Auto-título en sus dos fases.
- Mensaje con `provider="openai"`, `model`, usage y costo.
- Costo `null` sin precio y calculado con precio cargado.
- Filtro de consumo por OpenAI.
- Cancelación a mitad del stream → mensaje `interrupted`.

### Instalador

- `build.ps1 -SkipInstaller` incluye `openai` y sus dependencias.
- El bundle arranca sin `.git` y reporta la versión incrustada.
- Un turno OpenAI funciona desde el bundle.

---

## 11. Riesgos y decisiones abiertas

| Riesgo | Mitigación / decisión requerida |
|---|---|
| Responses exige conservar items de razonamiento para tool loops | Test de segundo request con razonamiento y preservación completa de output items |
| `models.list` no garantiza capacidades por modelo | Filtrado conservador más prueba explícita del modelo seleccionado |
| Schemas neutrales no cumplen strict mode | Empezar con `strict=false` y cubrir compatibilidad antes de endurecer |
| Reasoning tokens pueden elevar costos | Mapearlos dentro de output y exigir precio cargado antes de activar KPIs |
| Modelos futuros con IDs nuevos | No usar whitelist cerrada; excluir solo familias claramente incompatibles |
| Catálogo visible pero modelo no habilitado para la organización | Validar el modelo elegido antes de activarlo y mostrar error accionable |
| Reintentos duplican solicitudes facturables | Limitar intentos, registrar modelo/status y documentar costo potencial |
| OpenAI API key compartida con datos del ERP | Confirmación de activación y misma política de proveedores externos que Gemini |

---

## 12. Verificación final

- [ ] Dependencia fijada y `uv.lock` actualizado.
- [ ] Backend lint, Pyright strict y suite completa en verde.
- [ ] Frontend type-check, tests de recomendación y build en verde.
- [ ] Tests unitarios de probe, runner, mapping, títulos y no-filtración.
- [ ] E2E completo en OpenAI, Gemini y Claude.
- [ ] Prueba real con API key de OpenAI sin registrar la key.
- [ ] `build.ps1` completo y smoke test del bundle.
- [ ] Documentación de precios y modelos actualizada con datos verificados de
      la cuenta usada en la prueba.
